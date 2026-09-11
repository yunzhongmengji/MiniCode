"""Evaluate tool-use expectations against one validated run trace."""

from dataclasses import dataclass

from minicode.core.events import EventKind
from minicode.core.replay import RunReplay
from minicode.evaluation_case import TraceExpectations


@dataclass(frozen=True, slots=True)
class TraceEvaluation:
    """Describe whether one run satisfied its tool-use contract."""

    missing_required_tools: tuple[str, ...]
    requested_forbidden_tools: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return whether the trace has no missing or forbidden tools."""
        return not self.missing_required_tools and not self.requested_forbidden_tools


def evaluate_trace_expectations(
    *,
    replay: RunReplay,
    expectations: TraceExpectations,
) -> TraceEvaluation:
    """Compare successful executions and requests with one case contract."""
    successful_tools: set[str] = set()
    requested_tools: set[str] = set()

    for event in replay.events:
        if event.kind is EventKind.TOOL_POLICY_DECIDED:
            requested_tools.add(_tool_name(event.payload.get("tool_name")))

        if (
            event.kind is EventKind.TOOL_EXECUTION_FINISHED
            and event.payload.get("outcome") == "succeeded"
        ):
            successful_tools.add(_tool_name(event.payload.get("tool_name")))

    return TraceEvaluation(
        missing_required_tools=tuple(
            tool
            for tool in expectations.required_successful_tools
            if tool not in successful_tools
        ),
        requested_forbidden_tools=tuple(
            tool
            for tool in expectations.forbidden_tool_requests
            if tool in requested_tools
        ),
    )


def _tool_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("tool event must contain a string tool_name")

    return value
