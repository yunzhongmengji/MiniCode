from minicode.core.events import EventKind, LedgerEvent
from minicode.core.replay import RunReplay
from minicode.evaluation_case import TraceExpectations
from minicode.evaluation_trace import (
    TraceEvaluation,
    evaluate_trace_expectations,
)


def _replay(*events: tuple[EventKind, dict[str, object]]) -> RunReplay:
    return RunReplay(
        events=tuple(
            LedgerEvent(
                run_id="run_001",
                sequence=sequence,
                kind=kind,
                payload=payload,
            )
            for sequence, (kind, payload) in enumerate(events, start=1)
        )
    )


def test_trace_evaluation_passes_when_tool_contract_is_satisfied() -> None:
    replay = _replay(
        (EventKind.RUN_STARTED, {}),
        (
            EventKind.TOOL_POLICY_DECIDED,
            {"tool_name": "read_file"},
        ),
        (
            EventKind.TOOL_EXECUTION_FINISHED,
            {
                "tool_name": "read_file",
                "outcome": "succeeded",
            },
        ),
        (EventKind.RUN_FINISHED, {"outcome": "succeeded"}),
    )

    evaluation = evaluate_trace_expectations(
        replay=replay,
        expectations=TraceExpectations(
            required_successful_tools=("read_file",),
            forbidden_tool_requests=("edit_file",),
        ),
    )

    assert evaluation == TraceEvaluation(
        missing_required_tools=(),
        requested_forbidden_tools=(),
    )
    assert evaluation.passed is True


def test_trace_evaluation_reports_missing_and_forbidden_tools() -> None:
    replay = _replay(
        (EventKind.RUN_STARTED, {}),
        (
            EventKind.TOOL_POLICY_DECIDED,
            {"tool_name": "edit_file"},
        ),
        (
            EventKind.TOOL_POLICY_DECIDED,
            {"tool_name": "run_tests"},
        ),
        (
            EventKind.TOOL_EXECUTION_FINISHED,
            {
                "tool_name": "run_tests",
                "outcome": "failed",
            },
        ),
        (EventKind.RUN_FINISHED, {"outcome": "failed"}),
    )

    evaluation = evaluate_trace_expectations(
        replay=replay,
        expectations=TraceExpectations(
            required_successful_tools=(
                "run_tests",
                "search_text",
            ),
            forbidden_tool_requests=(
                "create_file",
                "edit_file",
            ),
        ),
    )

    assert evaluation == TraceEvaluation(
        missing_required_tools=(
            "run_tests",
            "search_text",
        ),
        requested_forbidden_tools=("edit_file",),
    )
    assert evaluation.passed is False
