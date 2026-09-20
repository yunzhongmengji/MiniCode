"""Budget pressure measurement and pure context-editing planning."""

from collections.abc import Collection
from dataclasses import dataclass

from minicode.core.context_profile import profile_model_request
from minicode.core.context_retention import (
    ToolResultRetentionPlan,
    plan_tool_result_retention,
)
from minicode.core.context_retrieval import (
    DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
    render_tool_result_reference,
)
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolResult
from minicode.tools.spec import ToolSpec


@dataclass(frozen=True, slots=True)
class ContextPressureDecision:
    """Compare one complete request with its byte budget."""

    request_bytes: int
    max_request_bytes: int

    def __post_init__(self) -> None:
        """Reject values that cannot describe a valid request budget."""
        _require_integer(self.request_bytes, "request_bytes")

        if self.request_bytes < 0:
            raise ValueError("request_bytes must not be negative")

        validate_max_request_bytes(self.max_request_bytes)

    @property
    def overflow_bytes(self) -> int:
        """Return how far the request exceeds its budget."""
        return max(0, self.request_bytes - self.max_request_bytes)

    @property
    def editing_required(self) -> bool:
        """Return whether a later planner must attempt context editing."""
        return self.overflow_bytes > 0


@dataclass(frozen=True, slots=True)
class ContextEditingPlan:
    """Describe a budget-driven selection without modifying the request."""

    pressure: ContextPressureDecision
    retention: ToolResultRetentionPlan
    selected_call_ids: tuple[str, ...]
    planned_request_bytes: int

    @property
    def total_bytes_saved(self) -> int:
        """Return the expected complete-request saving."""
        return self.pressure.request_bytes - self.planned_request_bytes

    @property
    def remaining_overflow_bytes(self) -> int:
        """Return bytes still above budget after the planned selections."""
        return max(0, self.planned_request_bytes - self.pressure.max_request_bytes)

    @property
    def budget_satisfied(self) -> bool:
        """Return whether the planned request fits the configured budget."""
        return self.remaining_overflow_bytes == 0


def assess_context_pressure(
    request: ModelRequest,
    *,
    max_request_bytes: int,
) -> ContextPressureDecision:
    """Decide whether the complete provider-neutral request exceeds its budget."""
    if not isinstance(request, ModelRequest):
        raise TypeError("request must be a ModelRequest")

    return ContextPressureDecision(
        request_bytes=profile_model_request(request).total_bytes,
        max_request_bytes=max_request_bytes,
    )


def validate_max_request_bytes(max_request_bytes: int) -> None:
    """Require a positive non-boolean request byte budget."""
    _require_integer(max_request_bytes, "max_request_bytes")

    if max_request_bytes <= 0:
        raise ValueError("max_request_bytes must be greater than zero")


def plan_context_editing(
    request: ModelRequest,
    *,
    max_request_bytes: int,
    retrieval_tool_spec: ToolSpec,
    protected_recent_batch_count: int = 1,
    excluded_tool_names: Collection[str] = frozenset(),
    max_retrievable_output_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
    minimum_net_savings_bytes: int = 1,
) -> ContextEditingPlan:
    """Select the oldest eligible results until the byte budget is met."""
    _require_retrieval_tool_spec(retrieval_tool_spec)

    _require_integer(minimum_net_savings_bytes, "minimum_net_savings_bytes")

    if minimum_net_savings_bytes <= 0:
        raise ValueError("minimum_net_savings_bytes must be greater than zero")

    pressure = assess_context_pressure(
        request,
        max_request_bytes=max_request_bytes,
    )
    retention = plan_tool_result_retention(
        request.conversation,
        protected_recent_batch_count=protected_recent_batch_count,
        excluded_tool_names=excluded_tool_names,
        max_retrievable_output_bytes=max_retrievable_output_bytes,
    )

    if not pressure.editing_required:
        return ContextEditingPlan(
            pressure=pressure,
            retention=retention,
            selected_call_ids=(),
            planned_request_bytes=pressure.request_bytes,
        )

    eligible_call_ids = frozenset(retention.eligible_call_ids)
    references: dict[str, ToolResult] = {}
    selected_call_ids: tuple[str, ...] = ()
    planned_request_bytes = pressure.request_bytes

    for item in request.conversation:
        if not isinstance(item, ToolResult) or item.call_id not in eligible_call_ids:
            continue

        original_output_bytes = len(item.output.encode("utf-8"))
        reference_output = render_tool_result_reference(
            call_id=item.call_id,
            original_output_bytes=original_output_bytes,
        )

        if len(reference_output.encode("utf-8")) >= original_output_bytes:
            continue

        references[item.call_id] = ToolResult(
            call_id=item.call_id,
            output=reference_output,
        )
        candidate_request = _request_with_references(
            request,
            references=references,
            retrieval_tool_spec=retrieval_tool_spec,
        )
        candidate_bytes = profile_model_request(candidate_request).total_bytes

        if pressure.request_bytes - candidate_bytes >= minimum_net_savings_bytes:
            selected_call_ids = tuple(references)
            planned_request_bytes = candidate_bytes

        if planned_request_bytes <= pressure.max_request_bytes:
            break

    return ContextEditingPlan(
        pressure=pressure,
        retention=retention,
        selected_call_ids=selected_call_ids,
        planned_request_bytes=planned_request_bytes,
    )


def apply_context_editing_plan(
    request: ModelRequest,
    plan: ContextEditingPlan,
    *,
    retrieval_tool_spec: ToolSpec,
) -> ModelRequest:
    """Materialize one verified plan without changing the canonical request."""
    if not isinstance(request, ModelRequest):
        raise TypeError("request must be a ModelRequest")

    if not isinstance(plan, ContextEditingPlan):
        raise TypeError("plan must be a ContextEditingPlan")

    _require_retrieval_tool_spec(retrieval_tool_spec)
    request_bytes = profile_model_request(request).total_bytes

    if request_bytes != plan.pressure.request_bytes:
        raise ValueError("context editing plan does not match request bytes")

    selected_call_ids = frozenset(plan.selected_call_ids)
    eligible_call_ids = frozenset(plan.retention.eligible_call_ids)

    if not selected_call_ids.issubset(eligible_call_ids):
        raise ValueError("context editing plan selected a protected tool result")

    if not selected_call_ids:
        if plan.planned_request_bytes != request_bytes:
            raise ValueError("empty context editing plan has inconsistent bytes")

        return request

    references: dict[str, ToolResult] = {}

    for item in request.conversation:
        if not isinstance(item, ToolResult) or item.call_id not in selected_call_ids:
            continue

        original_output_bytes = len(item.output.encode("utf-8"))
        references[item.call_id] = ToolResult(
            call_id=item.call_id,
            output=render_tool_result_reference(
                call_id=item.call_id,
                original_output_bytes=original_output_bytes,
            ),
            is_error=item.is_error,
        )

    if frozenset(references) != selected_call_ids:
        raise ValueError("context editing plan references missing tool results")

    projected_request = _request_with_references(
        request,
        references=references,
        retrieval_tool_spec=retrieval_tool_spec,
    )
    actual_bytes = profile_model_request(projected_request).total_bytes

    if actual_bytes != plan.planned_request_bytes:
        raise ValueError("context editing plan disagrees with projected request bytes")

    return projected_request


def _request_with_references(
    request: ModelRequest,
    *,
    references: dict[str, ToolResult],
    retrieval_tool_spec: ToolSpec,
) -> ModelRequest:
    """Build one temporary request used only for byte measurement."""
    conversation = tuple(
        references.get(item.call_id, item) if isinstance(item, ToolResult) else item
        for item in request.conversation
    )
    tool_specs = request.tool_specs

    if not any(spec.name == retrieval_tool_spec.name for spec in tool_specs):
        tool_specs = (*tool_specs, retrieval_tool_spec)

    return ModelRequest(
        conversation=conversation,
        tool_specs=tool_specs,
        instructions=request.instructions,
    )


def _require_retrieval_tool_spec(retrieval_tool_spec: object) -> None:
    """Require the exact kind of tool used by historical references."""
    if not isinstance(retrieval_tool_spec, ToolSpec):
        raise TypeError("retrieval_tool_spec must be a ToolSpec")

    if retrieval_tool_spec.name != "read_tool_result":
        raise ValueError("retrieval_tool_spec must describe read_tool_result")


def _require_integer(value: object, field_name: str) -> None:
    """Require a non-boolean integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
