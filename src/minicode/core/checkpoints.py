"""Resumable snapshots of query-loop state."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from minicode.core.conversation import (
    ConversationItem,
)
from minicode.core.messages import Message
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    """State required to resume one query-loop run."""

    run_id: str
    message_history: Sequence[ConversationItem]
    turns_used: int
    tool_calls_used: int

    def __post_init__(self) -> None:
        """Validate and snapshot resumable state."""
        if not isinstance(self.run_id, str):
            raise TypeError("run_id must be a string")

        if not self.run_id.strip():
            raise ValueError("run_id must not be blank")

        if not isinstance(
            self.message_history,
            Sequence,
        ) or isinstance(
            self.message_history,
            (str, bytes),
        ):
            raise TypeError("message_history must be a sequence")

        seen_tool_call_ids: set[str] = set()
        completed_tool_call_ids: set[str] = set()

        for item in self.message_history:
            if not isinstance(
                item,
                (
                    Message,
                    ToolCall,
                    ToolResult,
                ),
            ):
                raise TypeError(
                    "message_history must contain only ConversationItem instances"
                )

            if isinstance(
                item,
                ToolCall,
            ):
                if item.call_id in seen_tool_call_ids:
                    raise ValueError("tool call ids must be unique")

                seen_tool_call_ids.add(item.call_id)

            elif isinstance(
                item,
                ToolResult,
            ):
                if item.call_id not in seen_tool_call_ids:
                    raise ValueError("tool result must match a preceding tool call")

                if item.call_id in completed_tool_call_ids:
                    raise ValueError("each tool call must have at most one result")

                completed_tool_call_ids.add(item.call_id)

        counters = (
            (
                "turns_used",
                self.turns_used,
            ),
            (
                "tool_calls_used",
                self.tool_calls_used,
            ),
        )

        for field_name, value in counters:
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")

            if value < 0:
                raise ValueError(f"{field_name} must not be negative")

        if self.tool_calls_used != len(completed_tool_call_ids):
            raise ValueError("tool_calls_used must equal completed tool calls")

        object.__setattr__(
            self,
            "message_history",
            tuple(self.message_history),
        )

    @property
    def pending_tool_calls(
        self,
    ) -> tuple[ToolCall, ...]:
        """Return tool calls without matching results."""
        completed_call_ids = {
            item.call_id
            for item in self.message_history
            if isinstance(
                item,
                ToolResult,
            )
        }

        return tuple(
            item
            for item in self.message_history
            if isinstance(
                item,
                ToolCall,
            )
            and item.call_id not in completed_call_ids
        )


class CheckpointStore(Protocol):
    """Save and retrieve resumable run checkpoints."""

    def save(
        self,
        checkpoint: RunCheckpoint,
    ) -> None:
        """Save one checkpoint."""
        ...

    def latest(
        self,
        run_id: str,
    ) -> RunCheckpoint | None:
        """Return the latest checkpoint for a run."""
        ...


class InMemoryCheckpointStore:
    """Store checkpoints in process memory."""

    def __init__(self) -> None:
        self._checkpoints_by_run_id: dict[
            str,
            list[RunCheckpoint],
        ] = {}

    def save(
        self,
        checkpoint: RunCheckpoint,
    ) -> None:
        """Append one checkpoint for its run."""
        if not isinstance(
            checkpoint,
            RunCheckpoint,
        ):
            raise TypeError("checkpoint must be a RunCheckpoint")

        checkpoints = self._checkpoints_by_run_id.setdefault(
            checkpoint.run_id,
            [],
        )
        checkpoints.append(checkpoint)

    def latest(
        self,
        run_id: str,
    ) -> RunCheckpoint | None:
        """Return the most recently saved checkpoint."""
        checkpoints = self._checkpoints_by_run_id.get(run_id)

        if not checkpoints:
            return None

        return checkpoints[-1]
