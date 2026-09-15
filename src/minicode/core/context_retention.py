"""Retention rules for model-visible tool results."""

from collections.abc import Sequence
from dataclasses import dataclass

from minicode.core.conversation import ConversationItem
from minicode.core.tool_calls import ToolResult


@dataclass(frozen=True, slots=True)
class ToolResultRetentionPlan:
    """Classify tool results without changing canonical history."""

    protected_call_ids: tuple[str, ...]
    eligible_call_ids: tuple[str, ...]


def plan_tool_result_retention(
    conversation: Sequence[ConversationItem],
) -> ToolResultRetentionPlan:
    """Protect unseen trailing results and all error results."""
    latest_batch_call_ids = _latest_tool_result_batch_call_ids(conversation)
    protected_call_ids: list[str] = []
    eligible_call_ids: list[str] = []

    for item in conversation:
        if not isinstance(item, ToolResult):
            continue

        if item.is_error or item.call_id in latest_batch_call_ids:
            protected_call_ids.append(item.call_id)
        else:
            eligible_call_ids.append(item.call_id)

    return ToolResultRetentionPlan(
        protected_call_ids=tuple(protected_call_ids),
        eligible_call_ids=tuple(eligible_call_ids),
    )


def _latest_tool_result_batch_call_ids(
    conversation: Sequence[ConversationItem],
) -> frozenset[str]:
    """Return call IDs for consecutive tool results at history tail."""
    call_ids: set[str] = set()

    for item in reversed(conversation):
        if not isinstance(item, ToolResult):
            break

        call_ids.add(item.call_id)

    return frozenset(call_ids)
