"""Retrieval of original tool results from canonical conversation history."""

import json
from collections.abc import Sequence

from minicode.core.checkpoints import CheckpointStore
from minicode.core.conversation import ConversationItem
from minicode.core.tool_calls import ToolCall, ToolResult

DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES = 50_000


def render_tool_result_reference(
    *,
    call_id: str,
    original_output_bytes: int,
) -> str:
    """Render the stable reference understood by historical-result retrieval."""
    return json.dumps(
        {
            "call_id": call_id,
            "kind": "historical_tool_result_reference",
            "original_output_bytes": original_output_bytes,
            "retrieval_tool": "read_tool_result",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class ToolResultLookupError(LookupError):
    """Base exception for failed tool-result lookups."""


class UnknownToolCallError(ToolResultLookupError):
    """Raised when a conversation does not contain the requested tool call."""


class PendingToolResultError(ToolResultLookupError):
    """Raised when the requested tool call does not have a result yet."""


class RunHistoryNotFoundError(ToolResultLookupError):
    """Raised when no checkpoint exists for the bound run."""


class RunHistoryMismatchError(ToolResultLookupError):
    """Raised when a checkpoint store returns another run's history."""


def get_tool_result(
    conversation: Sequence[ConversationItem],
    call_id: str,
) -> ToolResult:
    """Return the original result for one tool call in canonical history."""
    if not isinstance(call_id, str):
        raise TypeError("call_id must be a string")

    if not call_id.strip():
        raise ValueError("call_id must not be blank")

    matching_call_found = False

    for item in conversation:
        if isinstance(item, ToolCall) and item.call_id == call_id:
            matching_call_found = True
        elif isinstance(item, ToolResult) and item.call_id == call_id:
            return item

    if matching_call_found:
        raise PendingToolResultError(f"tool call has no result yet: {call_id}")

    raise UnknownToolCallError(f"tool call not found: {call_id}")


class RunToolResultSource:
    """Read tool results from the latest checkpoint of one bound run."""

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        *,
        run_id: str,
    ) -> None:
        if not isinstance(run_id, str):
            raise TypeError("run_id must be a string")

        if not run_id.strip():
            raise ValueError("run_id must not be blank")

        self._checkpoint_store = checkpoint_store
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        """Return the only run this source may read."""
        return self._run_id

    def get(self, call_id: str) -> ToolResult:
        """Return one result from the bound run's latest checkpoint."""
        checkpoint = self._checkpoint_store.latest(self._run_id)

        if checkpoint is None:
            raise RunHistoryNotFoundError(
                f"no checkpoint found for run: {self._run_id}"
            )

        if checkpoint.run_id != self._run_id:
            raise RunHistoryMismatchError(
                "checkpoint run_id does not match tool-result source run_id"
            )

        return get_tool_result(checkpoint.message_history, call_id)
