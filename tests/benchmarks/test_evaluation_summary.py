import hashlib
import json
from pathlib import Path

import pytest

from minicode.evaluation_summary import (
    summarize_context_experiment_results,
    summarize_results,
)


def _write_result(
    root: Path,
    *,
    case_id: str,
    accepted: bool,
    model_calls: int,
    tool_executions: int,
    input_tokens: int,
    output_tokens: int,
    workspace_changes: list[str],
    schema_version: int = 1,
    verdict: dict[str, bool] | None = None,
    directory_name: str | None = None,
    run_id: str | None = None,
    context_experiment: dict[str, object] | None = None,
) -> None:
    case_root = root / (case_id if directory_name is None else directory_name)
    case_root.mkdir()
    result = {
        "schema_version": schema_version,
        "case_id": case_id,
        "accepted": accepted,
        "agent_exit_code": 0,
        "model": "test-model",
        "minicode_commit": "1234567890abcdef",
        "minicode_dirty": False,
        "run": {
            "outcome": "succeeded",
            "model_call_count": model_calls,
            "tool_execution_count": tool_executions,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "workspace_status": workspace_changes,
    }

    if run_id is not None:
        result["run"]["run_id"] = run_id

    if context_experiment is not None:
        result["context_experiment"] = context_experiment

    if verdict is not None:
        result["verdict"] = verdict

    answer = b"Recorded answer.\n"
    trace = b"Recorded trace.\n"
    (case_root / "answer.txt").write_bytes(answer)
    (case_root / "trace.txt").write_bytes(trace)
    result["artifacts"] = {
        "answer": {
            "file": "answer.txt",
            "sha256": hashlib.sha256(answer).hexdigest(),
        },
        "trace": {
            "file": "trace.txt",
            "sha256": hashlib.sha256(trace).hexdigest(),
        },
    }

    (case_root / "result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )


def _write_context_protocol(path: Path, *, repetitions: int = 2) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_id": "context-protocol-v1",
                "model": {"name": "test-model"},
                "cases": ["case_a"],
                "arms": {
                    "baseline": {"max_inline_tool_result_bytes": None},
                    "projection": {"max_inline_tool_result_bytes": 500},
                },
                "repetitions_per_case_per_arm": repetitions,
                "advancement_gates": {
                    "required_safe_task_successes_per_arm": repetitions,
                    "minimum_aggregate_input_token_reduction_percent": 5,
                    "maximum_per_case_input_token_regression_percent": 5,
                    "maximum_failed_or_cancelled_readbacks": 0,
                },
            }
        ),
        encoding="utf-8",
    )


def _context_experiment(
    arm: str,
    *,
    failed_readbacks: int = 0,
    protocol_id: str = "context-protocol-v1",
) -> dict[str, object]:
    projected = arm == "projection"
    saved_bytes = 10 if projected else 0
    return {
        "protocol_id": protocol_id,
        "arm": arm,
        "max_inline_tool_result_bytes": 500 if projected else None,
        "trace_configuration": {
            "configuration_schema_version": 2,
            "strategy": "tool_result_reference" if projected else "identity",
            "max_inline_tool_result_bytes": 500 if projected else None,
            "minimum_net_savings_bytes": 1 if projected else None,
            "retrieval_tool_loading": "on_reference" if projected else None,
        },
        "metrics": {
            "model_call_count": 1,
            "model_visible_bytes": 90 if projected else 100,
            "canonical_bytes": 100,
            "projection_bytes_saved": saved_bytes,
            "changed_tool_result_count": 1 if projected else 0,
            "successful_readback_count": 0,
            "failed_readback_count": failed_readbacks,
            "cancelled_readback_count": 0,
        },
    }


def test_summary_combines_recorded_results(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        case_id="case_a",
        accepted=True,
        model_calls=2,
        tool_executions=3,
        input_tokens=100,
        output_tokens=20,
        workspace_changes=[" M source.py"],
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "passed": True,
        },
    )
    _write_result(
        tmp_path,
        case_id="case_b",
        accepted=True,
        model_calls=1,
        tool_executions=0,
        input_tokens=40,
        output_tokens=10,
        workspace_changes=[],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": False,
            "budget_passed": False,
            "trace_passed": False,
            "passed": False,
        },
    )

    summary = summarize_results(tmp_path)

    assert "| case_a | yes | 2 | 3 | 100 | 20 | 1 |" in summary
    assert "| case_b | no | 1 | 0 | 40 | 10 | 0 |" in summary
    assert "- Passed: 1/2 (50.0%)" in summary
    assert "- Outcome failures: 0" in summary
    assert "- Operational failures: 1" in summary
    assert "- Budget failures: 1" in summary
    assert "- Trace failures: 1" in summary
    assert "- Legacy results without budget verdict: 0" in summary
    assert "- Legacy results without trace verdict: 1" in summary
    assert "- Total model calls: 3" in summary
    assert "- Total tool executions: 3" in summary
    assert "- Total input tokens: 140" in summary
    assert "- Total output tokens: 30" in summary
    assert "- Models: test-model" in summary
    assert "- MiniCode commits: 1234567" in summary


def test_summary_keeps_legacy_result_without_verdict(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        case_id="legacy_case",
        accepted=False,
        model_calls=1,
        tool_executions=0,
        input_tokens=10,
        output_tokens=5,
        workspace_changes=[],
    )

    summary = summarize_results(tmp_path)

    assert "| legacy_case | no | 1 | 0 | 10 | 5 | 0 |" in summary
    assert "- Passed: 0/1 (0.0%)" in summary
    assert "- Outcome failures: 1" in summary
    assert "- Operational failures: 0" in summary
    assert "- Budget failures: 0" in summary
    assert "- Trace failures: 0" in summary
    assert "- Legacy results without budget verdict: 1" in summary
    assert "- Legacy results without trace verdict: 1" in summary


def test_summary_rejects_inconsistent_trace_verdict(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        case_id="case",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=10,
        output_tokens=5,
        workspace_changes=[],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": False,
            "passed": True,
        },
    )

    with pytest.raises(
        ValueError,
        match="verdict passed is inconsistent",
    ):
        summarize_results(tmp_path)


def test_summary_rejects_tampered_artifact(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        case_id="case",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=10,
        output_tokens=5,
        workspace_changes=[],
    )
    (tmp_path / "case" / "answer.txt").write_text(
        "Tampered answer.\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="artifact SHA-256 mismatch",
    ):
        summarize_results(tmp_path)


def test_summary_rejects_directory_without_results(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="no result.json files found",
    ):
        summarize_results(tmp_path)


def test_context_summary_passes_complete_quality_and_token_gates(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path)

    for arm, tokens in (("baseline", (100, 100)), ("projection", (80, 90))):
        for repetition, input_tokens in enumerate(tokens, start=1):
            _write_result(
                results_root,
                case_id="case_a",
                accepted=True,
                model_calls=1,
                tool_executions=1,
                input_tokens=input_tokens,
                output_tokens=10,
                workspace_changes=[],
                schema_version=2,
                verdict={
                    "outcome_passed": True,
                    "operational_passed": True,
                    "budget_passed": True,
                    "trace_passed": True,
                    "passed": True,
                },
                directory_name=f"case_a-{arm}-{repetition}",
                run_id=f"run_{arm}_{repetition}",
                context_experiment=_context_experiment(arm),
            )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "| case_a | baseline | 2 | 2/2 | 200 | 20 | 0/0/0 |" in summary
    assert "| case_a | projection | 2 | 2/2 | 170 | 20 | 0/0/0 |" in summary
    assert "| case_a | 200 | 170 | -15.0% | pass |" in summary
    assert "- Repetitions complete: yes" in summary
    assert "- Safe Task Success: baseline 2/2, projection 2/2 (pass)" in summary
    assert "- Aggregate input Token reduction: 15.0% (pass)" in summary
    assert "- Failed or cancelled readbacks: 0 (pass)" in summary
    assert "- Advancement gate: PASS" in summary


def test_context_summary_fails_incomplete_repetitions_and_readback_gate(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path)

    for repetition in (1, 2):
        _write_result(
            results_root,
            case_id="case_a",
            accepted=True,
            model_calls=1,
            tool_executions=1,
            input_tokens=100,
            output_tokens=10,
            workspace_changes=[],
            schema_version=2,
            verdict={
                "outcome_passed": True,
                "operational_passed": True,
                "budget_passed": True,
                "trace_passed": True,
                "passed": True,
            },
            directory_name=f"case_a-baseline-{repetition}",
            run_id=f"run_baseline_{repetition}",
            context_experiment=_context_experiment("baseline"),
        )

    _write_result(
        results_root,
        case_id="case_a",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=90,
        output_tokens=10,
        workspace_changes=[],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": True,
            "passed": True,
        },
        directory_name="case_a-projection-1",
        run_id="run_projection_1",
        context_experiment=_context_experiment(
            "projection",
            failed_readbacks=1,
        ),
    )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Repetitions complete: no" in summary
    assert "- Safe Task Success: baseline 2/2, projection 1/2 (fail)" in summary
    assert "- Failed or cancelled readbacks: 1 (fail)" in summary
    assert "- Advancement gate: FAIL" in summary


def test_context_summary_rejects_result_from_another_protocol(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1)
    _write_result(
        results_root,
        case_id="case_a",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=100,
        output_tokens=10,
        workspace_changes=[],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": True,
            "passed": True,
        },
        directory_name="case_a-baseline-1",
        run_id="run_baseline_1",
        context_experiment=_context_experiment(
            "baseline",
            protocol_id="different-protocol",
        ),
    )

    with pytest.raises(
        ValueError,
        match="protocol_id does not match",
    ):
        summarize_context_experiment_results(results_root, protocol_path)


def test_context_summary_rejects_missing_versioned_trace_configuration(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1)
    context_experiment = _context_experiment("projection")
    trace_configuration = context_experiment["trace_configuration"]
    assert isinstance(trace_configuration, dict)
    del trace_configuration["retrieval_tool_loading"]
    _write_result(
        results_root,
        case_id="case_a",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=90,
        output_tokens=10,
        workspace_changes=[],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": True,
            "passed": True,
        },
        run_id="run_projection_1",
        context_experiment=context_experiment,
    )

    with pytest.raises(
        ValueError,
        match="context trace configuration is missing retrieval_tool_loading",
    ):
        summarize_context_experiment_results(results_root, protocol_path)
