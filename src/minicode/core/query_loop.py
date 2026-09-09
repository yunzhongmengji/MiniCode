"""Core orchestration for MiniCode's model query loop."""

import asyncio
from collections.abc import (
    Awaitable,
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from minicode.core.checkpoints import (
    CheckpointStore,
    RunCheckpoint,
)
from minicode.core.conversation import ConversationItem
from minicode.core.events import (
    EventKind,
    EventLedger,
)
from minicode.core.messages import Message, MessageRole
from minicode.core.model import Model, ModelRequest, ModelResponse
from minicode.core.tool_calls import (
    JsonValue,
    ToolCall,
)
from minicode.core.tool_runtime import ToolRuntime
from minicode.tools.spec import ToolSpec


class StopReason(StrEnum):
    """Reasons why a query-loop run stopped."""

    COMPLETED = "completed"
    TOOL_CALLS_PENDING = "tool_calls_pending"
    MAX_TURNS = "max_turns"
    MAX_TOOL_CALLS = "max_tool_calls"


@dataclass(frozen=True, slots=True)
class RunResult:
    """The observable result of a query-loop run."""

    stop_reason: StopReason
    response: ModelResponse
    message_history: tuple[ConversationItem, ...]
    turns_used: int

    def __post_init__(self) -> None:
        """Validate query-loop result invariants."""
        if not isinstance(self.turns_used, int) or isinstance(
            self.turns_used,
            bool,
        ):
            raise TypeError("turns_used must be an integer")

        if self.turns_used <= 0:
            raise ValueError("turns_used must be greater than zero")

        if self.stop_reason is StopReason.COMPLETED and self.response.tool_calls:
            raise ValueError("completed result must not contain tool calls")

        if (
            self.stop_reason
            in (
                StopReason.TOOL_CALLS_PENDING,
                StopReason.MAX_TURNS,
                StopReason.MAX_TOOL_CALLS,
            )
            and not self.response.tool_calls
        ):
            raise ValueError("non-completed result must contain tool calls")


class QueryLoop:
    """Coordinate model calls without depending on a provider SDK."""

    def __init__(
        self,
        model: Model,
        max_turns: int = 1,
        tool_runtime: ToolRuntime | None = None,
        max_tool_calls: int = 8,
        tool_specs: Sequence[ToolSpec] = (),
        total_timeout_seconds: float | None = None,
        event_ledger: EventLedger | None = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        if not isinstance(max_turns, int) or isinstance(max_turns, bool):
            raise TypeError("max_turns must be an integer")

        if max_turns <= 0:
            raise ValueError("max_turns must be greater than zero")

        if not isinstance(max_tool_calls, int) or isinstance(
            max_tool_calls,
            bool,
        ):
            raise TypeError("max_tool_calls must be an integer")

        if max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be greater than zero")

        if total_timeout_seconds is not None:
            if isinstance(
                total_timeout_seconds,
                bool,
            ) or not isinstance(
                total_timeout_seconds,
                (int, float),
            ):
                raise TypeError("total_timeout_seconds must be a number or None")

            normalized_total_timeout_seconds = float(total_timeout_seconds)

            if (
                not isfinite(normalized_total_timeout_seconds)
                or normalized_total_timeout_seconds <= 0
            ):
                raise ValueError(
                    "total_timeout_seconds must be finite and greater than zero"
                )
        else:
            normalized_total_timeout_seconds = None

        if not isinstance(tool_specs, Sequence) or isinstance(
            tool_specs,
            (str, bytes),
        ):
            raise TypeError("tool_specs must be a sequence")

        for tool_spec in tool_specs:
            if not isinstance(tool_spec, ToolSpec):
                raise TypeError("tool_specs must contain only ToolSpec instances")

        if checkpoint_store is not None and event_ledger is None:
            raise ValueError("checkpoint_store requires an event_ledger")

        self._model = model
        self._max_turns = max_turns
        self._tool_runtime = tool_runtime
        self._max_tool_calls = max_tool_calls
        self._tool_specs = tuple(tool_specs)
        self._total_timeout_seconds = normalized_total_timeout_seconds
        self._event_ledger = event_ledger
        self._checkpoint_store = checkpoint_store

    def _record_event(
        self,
        kind: EventKind,
        payload: Mapping[str, JsonValue],
    ) -> None:
        """Record an event when a ledger is configured."""
        if self._event_ledger is None:
            return

        self._event_ledger.record(
            kind,
            payload,
        )

    def _save_checkpoint(
        self,
        *,
        message_history: Sequence[ConversationItem],
        turns_used: int,
        tool_calls_used: int,
    ) -> None:
        """Save resumable state when configured."""
        checkpoint_store = self._checkpoint_store

        if checkpoint_store is None:
            return

        event_ledger = self._event_ledger

        if event_ledger is None:
            raise RuntimeError("checkpoint_store requires an event_ledger")

        checkpoint = RunCheckpoint(
            run_id=event_ledger.run_id,
            message_history=message_history,
            turns_used=turns_used,
            tool_calls_used=tool_calls_used,
        )

        checkpoint_store.save(checkpoint)

        self._record_event(
            EventKind.CHECKPOINT_SAVED,
            {
                "turns_used": (checkpoint.turns_used),
                "tool_calls_used": (checkpoint.tool_calls_used),
                "message_history_items": len(checkpoint.message_history),
            },
        )

    async def _execute_with_run_boundary(
        self,
        operation: Awaitable[RunResult],
    ) -> RunResult:
        """Execute one run operation with shared observation."""
        try:
            async with asyncio.timeout(self._total_timeout_seconds):
                result = await operation
        except asyncio.CancelledError:
            self._record_event(
                EventKind.RUN_FINISHED,
                {
                    "outcome": "cancelled",
                },
            )
            raise
        except TimeoutError:
            self._record_event(
                EventKind.RUN_FINISHED,
                {
                    "outcome": "timed_out",
                },
            )
            raise
        except Exception as error:
            self._record_event(
                EventKind.RUN_FINISHED,
                {
                    "outcome": "failed",
                    "error_type": (type(error).__name__),
                },
            )
            raise

        self._record_event(
            EventKind.RUN_FINISHED,
            {
                "outcome": "succeeded",
                "stop_reason": (result.stop_reason.value),
                "turns_used": result.turns_used,
            },
        )

        return result

    async def run(
        self,
        messages: Sequence[ConversationItem],
    ) -> RunResult:
        """Run the query loop within its total timeout."""
        self._record_event(
            EventKind.RUN_STARTED,
            {
                "initial_history_items": len(messages),
                "max_turns": self._max_turns,
                "max_tool_calls": (self._max_tool_calls),
                "total_timeout_seconds": (self._total_timeout_seconds),
            },
        )

        return await self._execute_with_run_boundary(self._run(messages))

    async def _resume_from_checkpoint(
        self,
        checkpoint: RunCheckpoint,
        *,
        pending_tool_calls: tuple[
            ToolCall,
            ...,
        ],
        first_turn: int,
    ) -> RunResult:
        """Complete pending tools and continue model turns."""
        message_history = tuple(checkpoint.message_history)
        tool_calls_used = checkpoint.tool_calls_used

        for tool_call in pending_tool_calls:
            tool_runtime = self._tool_runtime

            if tool_runtime is None:
                raise RuntimeError(
                    "cannot resume pending tool calls without a tool runtime"
                )

            tool_result = await tool_runtime.execute(tool_call)
            tool_calls_used += 1
            message_history += (tool_result,)

            self._save_checkpoint(
                message_history=message_history,
                turns_used=(checkpoint.turns_used),
                tool_calls_used=(tool_calls_used),
            )

        return await self._run(
            message_history,
            first_turn=first_turn,
            tool_calls_used=tool_calls_used,
        )

    async def resume(
        self,
        checkpoint: RunCheckpoint,
    ) -> RunResult:
        """Resume execution from a saved checkpoint."""
        if not isinstance(
            checkpoint,
            RunCheckpoint,
        ):
            raise TypeError("checkpoint must be a RunCheckpoint")

        event_ledger = self._event_ledger

        if event_ledger is not None and event_ledger.run_id != checkpoint.run_id:
            raise ValueError("checkpoint run_id does not match event ledger run_id")

        pending_tool_calls = checkpoint.pending_tool_calls

        if pending_tool_calls and self._tool_runtime is None:
            raise RuntimeError(
                "cannot resume pending tool calls without a tool runtime"
            )

        if checkpoint.tool_calls_used + len(pending_tool_calls) > self._max_tool_calls:
            raise ValueError("checkpoint exceeds the tool-call budget")

        first_turn = checkpoint.turns_used + 1

        if first_turn > self._max_turns:
            raise ValueError("checkpoint has exhausted the turn budget")

        self._record_event(
            EventKind.RUN_RESUMED,
            {
                "message_history_items": len(checkpoint.message_history),
                "turns_used": (checkpoint.turns_used),
                "tool_calls_used": (checkpoint.tool_calls_used),
                "pending_tool_call_count": len(pending_tool_calls),
            },
        )

        return await self._execute_with_run_boundary(
            self._resume_from_checkpoint(
                checkpoint,
                pending_tool_calls=(pending_tool_calls),
                first_turn=first_turn,
            )
        )

    async def _run(
        self,
        messages: Sequence[ConversationItem],
        *,
        first_turn: int = 1,
        tool_calls_used: int = 0,
    ) -> RunResult:
        """Run model turns until completion or a controlled stop."""
        message_history = tuple(messages)

        for turn in range(
            first_turn,
            self._max_turns + 1,
        ):
            request = ModelRequest(
                conversation=message_history,
                tool_specs=self._tool_specs,
            )
            self._record_event(
                EventKind.MODEL_CALL_STARTED,
                {
                    "turn": turn,
                },
            )

            try:
                response = await self._model.complete(request)
            except asyncio.CancelledError:
                self._record_event(
                    EventKind.MODEL_CALL_FINISHED,
                    {
                        "turn": turn,
                        "outcome": "cancelled",
                    },
                )
                raise
            except Exception as error:
                self._record_event(
                    EventKind.MODEL_CALL_FINISHED,
                    {
                        "turn": turn,
                        "outcome": "failed",
                        "error_type": type(error).__name__,
                    },
                )
                raise

            model_call_finished_payload: dict[
                str,
                JsonValue,
            ] = {
                "turn": turn,
                "outcome": "succeeded",
                "tool_call_count": len(response.tool_calls),
            }

            if response.usage is not None:
                model_call_finished_payload["input_tokens"] = (
                    response.usage.input_tokens
                )
                model_call_finished_payload["output_tokens"] = (
                    response.usage.output_tokens
                )

            self._record_event(
                EventKind.MODEL_CALL_FINISHED,
                model_call_finished_payload,
            )

            if not response.tool_calls:
                return RunResult(
                    stop_reason=StopReason.COMPLETED,
                    response=response,
                    message_history=message_history,
                    turns_used=turn,
                )

            if self._tool_runtime is None:
                return RunResult(
                    stop_reason=StopReason.TOOL_CALLS_PENDING,
                    response=response,
                    message_history=message_history,
                    turns_used=turn,
                )

            if turn == self._max_turns:
                return RunResult(
                    stop_reason=StopReason.MAX_TURNS,
                    response=response,
                    message_history=message_history,
                    turns_used=turn,
                )

            if tool_calls_used + len(response.tool_calls) > self._max_tool_calls:
                return RunResult(
                    stop_reason=StopReason.MAX_TOOL_CALLS,
                    response=response,
                    message_history=message_history,
                    turns_used=turn,
                )

            if response.content.strip():
                message_history += (
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=response.content,
                    ),
                )

            message_history += tuple(response.tool_calls)

            for tool_call in response.tool_calls:
                tool_result = await self._tool_runtime.execute(tool_call)
                tool_calls_used += 1
                message_history += (tool_result,)
                self._save_checkpoint(
                    message_history=message_history,
                    turns_used=turn,
                    tool_calls_used=tool_calls_used,
                )

        raise RuntimeError("query loop stopped without producing a result")
