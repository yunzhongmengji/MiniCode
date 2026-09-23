"""Evaluate tool-use expectations against one validated run trace."""

from dataclasses import dataclass

from minicode.core.events import EventKind
from minicode.core.replay import RunReplay
from minicode.evaluation_case import TraceExpectations, TraceExpectationsV3


@dataclass(frozen=True, slots=True)
class TraceEvaluation:
    """Describe whether one run satisfied its tool-use contract."""

    missing_required_tools: tuple[str, ...]
    requested_forbidden_tools: tuple[str, ...]
    successful_test_after_last_change: bool | None = None

    @property
    def passed(self) -> bool:
        """Return whether the trace has no missing or forbidden tools."""
        return (
            not self.missing_required_tools
            and not self.requested_forbidden_tools
            and self.successful_test_after_last_change is not False
        )


def evaluate_trace_expectations(
    *,
    replay: RunReplay,
    expectations: TraceExpectations | TraceExpectationsV3,
) -> TraceEvaluation:
    """Compare successful executions and requests with one case contract."""
    if isinstance(expectations, TraceExpectationsV3):
        coverage_tools = expectations.process_coverage_tools
        require_test_after_change = (
            expectations.require_successful_test_after_change
        )
    else:
        coverage_tools = expectations.required_successful_tools
        require_test_after_change = "run_tests" in coverage_tools

    successful_tools: set[str] = set()
    requested_tools: set[str] = set()
    last_successful_change_sequence: int | None = None
    last_successful_test_sequence: int | None = None

    for event in replay.events:
        if event.kind is EventKind.TOOL_POLICY_DECIDED:
            requested_tools.add(_tool_name(event.payload.get("tool_name")))

        if (
            event.kind is EventKind.TOOL_EXECUTION_FINISHED
            and event.payload.get("outcome") == "succeeded"
        ):
            tool_name = _tool_name(event.payload.get("tool_name"))
            successful_tools.add(tool_name)

            if tool_name in {"create_file", "edit_file"}:
                last_successful_change_sequence = event.sequence

            if tool_name == "run_tests":
                last_successful_test_sequence = event.sequence

    successful_test_after_last_change: bool | None = None

    if (
        last_successful_change_sequence is not None
        and require_test_after_change
    ):
        successful_test_after_last_change = (
            last_successful_test_sequence is not None
            and last_successful_test_sequence > last_successful_change_sequence
        )

    return TraceEvaluation(
        missing_required_tools=tuple(
            tool
            for tool in coverage_tools
            if tool not in successful_tools
        ),
        requested_forbidden_tools=tuple(
            tool
            for tool in expectations.forbidden_tool_requests
            if tool in requested_tools
        ),
        successful_test_after_last_change=successful_test_after_last_change,
    )


def _tool_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("tool event must contain a string tool_name")

    return value
