"""Explainable retention rules for model-visible tool results."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

from minicode.core.context_retrieval import DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES
from minicode.core.conversation import ConversationItem
from minicode.core.tool_calls import ToolCall, ToolResult


class ToolResultRetentionReason(StrEnum):
    """Why one historical tool result is protected or eligible."""

    PROTECTED_RECENT = "protected_recent"
    PROTECTED_ERROR = "protected_error"
    PROTECTED_EXCLUDED_TOOL = "protected_excluded_tool"
    PROTECTED_NOT_RETRIEVABLE = "protected_not_retrievable"
    ELIGIBLE = "eligible"


@dataclass(frozen=True, slots=True)
class ToolResultRetentionDecision:
    """One deterministic retention decision for one tool result."""

    call_id: str
    reason: ToolResultRetentionReason


@dataclass(frozen=True, slots=True)
class ToolResultRetentionPlan:
    """Classify tool results without changing canonical history."""

    decisions: tuple[ToolResultRetentionDecision, ...]

    @property
    def protected_call_ids(self) -> tuple[str, ...]:
        """Return result IDs that must remain complete."""
        return tuple(
            decision.call_id
            for decision in self.decisions
            if decision.reason is not ToolResultRetentionReason.ELIGIBLE
        )

    @property
    def eligible_call_ids(self) -> tuple[str, ...]:
        """Return result IDs that may enter a later selection step."""
        return tuple(
            decision.call_id
            for decision in self.decisions
            if decision.reason is ToolResultRetentionReason.ELIGIBLE
        )


def plan_tool_result_retention(
    conversation: Sequence[ConversationItem],
    *,
    protected_recent_batch_count: int = 1,
    excluded_tool_names: Collection[str] = frozenset(),
    max_retrievable_output_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
) -> ToolResultRetentionPlan:
    """Give every tool result one stable retention reason."""
    if isinstance(protected_recent_batch_count, bool) or not isinstance(
        protected_recent_batch_count, int
    ):
        raise TypeError("protected_recent_batch_count must be an integer")

    if protected_recent_batch_count <= 0:
        raise ValueError("protected_recent_batch_count must be greater than zero")

    if isinstance(excluded_tool_names, (str, bytes)) or not isinstance(
        excluded_tool_names, Collection
    ):
        raise TypeError("excluded_tool_names must be a collection")

    for tool_name in excluded_tool_names:
        if not isinstance(tool_name, str):
            raise TypeError("excluded_tool_names must contain only strings")

        if not tool_name.strip():
            raise ValueError("excluded_tool_names must not contain blank strings")

    if isinstance(max_retrievable_output_bytes, bool) or not isinstance(
        max_retrievable_output_bytes, int
    ):
        raise TypeError("max_retrievable_output_bytes must be an integer")

    if max_retrievable_output_bytes <= 0:
        raise ValueError("max_retrievable_output_bytes must be greater than zero")

    recent_batch_call_ids = _recent_tool_result_batch_call_ids(
        conversation,
        batch_count=protected_recent_batch_count,
    )
    tool_names_by_call_id = {
        item.call_id: item.name
        for item in conversation
        if isinstance(item, ToolCall)
    }
    decisions: list[ToolResultRetentionDecision] = []

    for item in conversation:
        if not isinstance(item, ToolResult):
            continue

        if item.call_id in recent_batch_call_ids:
            reason = ToolResultRetentionReason.PROTECTED_RECENT
        elif item.is_error:
            reason = ToolResultRetentionReason.PROTECTED_ERROR
        elif tool_names_by_call_id.get(item.call_id) in excluded_tool_names:
            reason = ToolResultRetentionReason.PROTECTED_EXCLUDED_TOOL
        elif len(item.output.encode("utf-8")) > max_retrievable_output_bytes:
            reason = ToolResultRetentionReason.PROTECTED_NOT_RETRIEVABLE
        else:
            reason = ToolResultRetentionReason.ELIGIBLE

        decisions.append(
            ToolResultRetentionDecision(
                call_id=item.call_id,
                reason=reason,
            )
        )

    return ToolResultRetentionPlan(decisions=tuple(decisions))


def _recent_tool_result_batch_call_ids(
    conversation: Sequence[ConversationItem],
    *,
    batch_count: int,
) -> frozenset[str]:
    """Return call IDs belonging to the newest result batches."""
    call_ids: set[str] = set()
    batches_seen = 0
    inside_batch = False
    found_trailing_result = False

    for item in reversed(conversation):
        if isinstance(item, ToolResult):
            found_trailing_result = True

            if not inside_batch:
                batches_seen += 1

                if batches_seen > batch_count:
                    break

                inside_batch = True

            call_ids.add(item.call_id)
            continue

        if not found_trailing_result:
            break

        inside_batch = False

    return frozenset(call_ids)
