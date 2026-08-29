"""Core orchestration for MiniCode's model query loop."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from minicode.core.conversation import ConversationItem
from minicode.core.messages import Message, MessageRole
from minicode.core.model import Model, ModelRequest, ModelResponse
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

        if not isinstance(tool_specs, Sequence) or isinstance(
            tool_specs,
            (str, bytes),
        ):
            raise TypeError("tool_specs must be a sequence")

        for tool_spec in tool_specs:
            if not isinstance(tool_spec, ToolSpec):
                raise TypeError("tool_specs must contain only ToolSpec instances")

        self._model = model
        self._max_turns = max_turns
        self._tool_runtime = tool_runtime
        self._max_tool_calls = max_tool_calls
        self._tool_specs = tuple(tool_specs)

    async def run(
        self,
        messages: Sequence[ConversationItem],
    ) -> RunResult:
        """Run model turns until completion or a controlled stop."""
        message_history = tuple(messages)
        tool_calls_used = 0

        for turn in range(1, self._max_turns + 1):
            request = ModelRequest(
                conversation=message_history,
                tool_specs=self._tool_specs,
            )
            response = await self._model.complete(request)

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

        raise RuntimeError("query loop stopped without producing a result")
