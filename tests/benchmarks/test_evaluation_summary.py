import hashlib
import json
from pathlib import Path

import pytest

from minicode.evaluation_archive import archive_formal_experiment
from minicode.evaluation_formal import (
    FormalRunRequest,
    run_budgeted_context_formal_experiment,
)
from minicode.evaluation_summary import (
    main,
    summarize_context_experiment_results,
    summarize_context_preflight_results,
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
    trace_evaluation: dict[str, object] | None = None,
    case_manifest: dict[str, object] | None = None,
) -> None:
    case_root = root / (case_id if directory_name is None else directory_name)
    case_root.mkdir(exist_ok=True)
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

    if case_manifest is not None:
        result["case_manifest"] = case_manifest

    if schema_version == 2 and verdict is not None:
        result["trace_evaluation"] = (
            trace_evaluation
            if trace_evaluation is not None
            else {
                "missing_required_tools": (
                    [] if verdict["trace_passed"] else ["fixture_required_tool"]
                ),
                "requested_forbidden_tools": [],
                "successful_test_after_last_change": None,
            }
        )

    answer = b"Recorded answer.\n"
    trace = b"Recorded trace.\n"
    workspace_patch = b""
    (case_root / "answer.txt").write_bytes(answer)
    (case_root / "trace.txt").write_bytes(trace)
    (case_root / "workspace.patch").write_bytes(workspace_patch)
    result["artifacts"] = {
        "answer": {
            "file": "answer.txt",
            "sha256": hashlib.sha256(answer).hexdigest(),
        },
        "trace": {
            "file": "trace.txt",
            "sha256": hashlib.sha256(trace).hexdigest(),
        },
        "workspace_patch": {
            "file": "workspace.patch",
            "sha256": hashlib.sha256(workspace_patch).hexdigest(),
        },
    }

    (case_root / "result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )


def _schema_3_case_manifest(
    case_id: str = "case_a",
    *,
    require_successful_test_after_change: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": 3,
        "case_id": case_id,
        "category": "fixture",
        "ground_truth": {
            "defined_by": "test",
            "evidence": ["acceptance.py"],
        },
        "allowed_changes": ["implementation.py"],
        "forbidden_actions": ["create files"],
        "trace_expectations": {
            "process_coverage_tools": ["list_files", "search_text", "read_file"],
            "forbidden_tool_requests": ["create_file"],
            "require_successful_test_after_change": (
                require_successful_test_after_change
            ),
        },
        "budget": {
            "max_turns": 3,
            "max_tool_calls": 4,
        },
    }


def _write_context_protocol(
    path: Path,
    *,
    repetitions: int = 2,
    schema_version: int = 1,
) -> None:
    baseline: dict[str, object] = {"max_inline_tool_result_bytes": None}
    projection: dict[str, object] = {"max_inline_tool_result_bytes": 500}

    if schema_version == 2:
        baseline.update(
            {
                "strategy": "identity",
                "minimum_net_savings_bytes": None,
                "retrieval_tool_loading": None,
            }
        )
        projection.update(
            {
                "strategy": "tool_result_reference",
                "minimum_net_savings_bytes": 1,
                "retrieval_tool_loading": "on_reference",
            }
        )

    payload: dict[str, object] = {
        "schema_version": schema_version,
        "protocol_id": f"context-protocol-v{schema_version}",
        "model": {"name": "test-model"},
        "cases": ["case_a"],
        "arms": {
            "baseline": baseline,
            "projection": projection,
        },
        "repetitions_per_case_per_arm": repetitions,
        "advancement_gates": {
            "required_safe_task_successes_per_arm": repetitions,
            "minimum_aggregate_input_token_reduction_percent": 5,
            "maximum_per_case_input_token_regression_percent": 5,
            "maximum_failed_or_cancelled_readbacks": 0,
        },
    }

    if schema_version == 2:
        payload["context_projection_configuration_schema_version"] = 2
        payload["preflight_plan"] = {
            "case": "case_a",
            "arm_order": ["baseline", "projection"],
            "runs": 2,
            "success_requirements": {
                "safe_task_successes_per_arm": 1,
                "minimum_changed_tool_result_count": 1,
                "maximum_failed_or_cancelled_readbacks": 0,
                "provider_usage_required": True,
                "complete_artifact_set_required": True,
            },
        }
        payload["preflight_budget"] = {
            "maximum_runs": 2,
            "maximum_input_tokens": 300,
            "maximum_output_tokens": 100,
        }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _context_experiment(
    arm: str,
    *,
    failed_readbacks: int = 0,
    protocol_id: str = "context-protocol-v1",
    changed_tool_result_count: int | None = None,
) -> dict[str, object]:
    projected = arm == "projection"
    changed_count = (
        int(projected)
        if changed_tool_result_count is None
        else changed_tool_result_count
    )
    saved_bytes = 10 if changed_count > 0 else 0
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
            "model_visible_bytes": 100 - saved_bytes,
            "canonical_bytes": 100,
            "projection_bytes_saved": saved_bytes,
            "changed_tool_result_count": changed_count,
            "successful_readback_count": 0,
            "failed_readback_count": failed_readbacks,
            "cancelled_readback_count": 0,
        },
    }


def _write_preflight_results(
    results_root: Path,
    protocol_path: Path,
    *,
    arms: tuple[str, ...] = ("baseline", "projection"),
    projection_changes: int = 1,
    failed_readbacks: int = 0,
    input_tokens: tuple[int, ...] = (100, 90),
) -> None:
    (results_root / "protocol.snapshot.json").write_bytes(protocol_path.read_bytes())

    for index, arm in enumerate(arms):
        _write_result(
            results_root,
            case_id="case_a",
            accepted=True,
            model_calls=1,
            tool_executions=1,
            input_tokens=input_tokens[index],
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
            directory_name=f"case_a-{arm}-{index}",
            run_id=f"run_{arm}_{index}",
            context_experiment=_context_experiment(
                arm,
                failed_readbacks=(failed_readbacks if arm == "projection" else 0),
                protocol_id="context-protocol-v2",
                changed_tool_result_count=(
                    projection_changes if arm == "projection" else 0
                ),
            ),
        )


def _write_budgeted_context_protocol(
    path: Path,
    *,
    formal_input_budget: int = 270_000,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (
            project_root
            / "benchmarks"
            / "context_projection"
            / "real_model_protocol_v4.json"
        ).read_text(encoding="utf-8")
    )
    payload["protocol_id"] = "budgeted-context-protocol-v4"
    payload["model"]["name"] = "test-model"
    payload["cases"] = ["case_a"]
    payload["preflight_plan"]["case"] = "case_a"
    payload["formal_budget"]["maximum_runs"] = 6
    payload["formal_budget"]["maximum_input_tokens"] = formal_input_budget
    payload["advancement_gates"][
        "required_safe_task_successes_per_arm"
    ] = 3
    path.write_text(json.dumps(payload), encoding="utf-8")


def _budgeted_context_experiment(arm: str) -> dict[str, object]:
    if arm == "baseline":
        return _context_experiment(
            arm,
            protocol_id="budgeted-context-protocol-v4",
        )

    return {
        "protocol_id": "budgeted-context-protocol-v4",
        "arm": "projection",
        "max_request_bytes": 10_000,
        "trace_configuration": {
            "configuration_schema_version": 3,
            "strategy": "budgeted_tool_result_reference",
            "max_request_bytes": 10_000,
            "protected_recent_batch_count": 2,
            "minimum_net_savings_bytes": 1,
            "excluded_tool_names": ["git_diff", "run_tests"],
            "max_retrievable_output_bytes": 50_000,
            "retrieval_tool_loading": "on_reference",
        },
        "metrics": {
            "model_call_count": 1,
            "model_visible_bytes": 90,
            "canonical_bytes": 100,
            "projection_bytes_saved": 10,
            "changed_tool_result_count": 1,
            "successful_readback_count": 0,
            "failed_readback_count": 0,
            "cancelled_readback_count": 0,
        },
    }


def _write_budgeted_preflight_results(
    results_root: Path,
    protocol_path: Path,
) -> None:
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    (results_root / "protocol.snapshot.json").write_bytes(protocol_bytes)
    runs = [
        {
            "run_index": index,
            "arm": arm,
            "result_directory": f"{index:02d}-{arm}",
        }
        for index, arm in enumerate(
            protocol["preflight_plan"]["arm_order"],
            start=1,
        )
    ]
    (results_root / "preflight-plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_id": protocol["protocol_id"],
                "protocol_snapshot_sha256": hashlib.sha256(
                    protocol_bytes
                ).hexdigest(),
                "case_id": protocol["preflight_plan"]["case"],
                "runs": runs,
            }
        ),
        encoding="utf-8",
    )
    events: list[dict[str, object]] = []

    for run in runs:
        identity = {
            "run_index": run["run_index"],
            "arm": run["arm"],
            "result_directory": run["result_directory"],
        }
        events.extend(
            (
                {"event": "run_started", **identity},
                {
                    "event": "run_finished",
                    **identity,
                    "passed": True,
                    "result_recorded": True,
                    "failure_reason": None,
                },
            )
        )

    (results_root / "preflight-events.jsonl").write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )

    for index, (arm, input_tokens) in enumerate(
        (("baseline", 100), ("projection", 90)),
        start=1,
    ):
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
            directory_name=f"{index:02d}-{arm}",
            run_id=f"run_{arm}_{index}",
            context_experiment=_budgeted_context_experiment(arm),
        )


def _write_budgeted_formal_results(
    results_root: Path,
    protocol_path: Path,
) -> None:
    class _FormalFixtureExecutor:
        def execute(self, request: FormalRunRequest) -> bool:
            input_tokens = 100 if request.arm == "baseline" else 90
            _write_result(
                request.result_directory.parent,
                case_id=request.case_id,
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
                directory_name=request.result_directory.name,
                run_id=f"run_{request.run_index}",
                context_experiment=_budgeted_context_experiment(request.arm),
            )
            return True

    run_budgeted_context_formal_experiment(
        protocol_path=protocol_path,
        results_root=results_root,
        executor=_FormalFixtureExecutor(),
    )


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


def test_context_preflight_summary_passes_complete_pair(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert "| baseline | 1 | 1/1 | 100 | 10 | 0 | 0/0 |" in summary
    assert "| projection | 1 | 1/1 | 90 | 10 | 1 | 0/0 |" in summary
    assert "- Run shape: pass" in summary
    assert "- Projection activity: 1/1 (pass)" in summary
    assert "- Provider input Token budget: 190/300 (pass)" in summary
    assert "- Per-run Artifact set: pass" in summary
    assert "- Protocol snapshot: pass" in summary
    assert "- Preflight gate: PASS" in summary


def test_budgeted_context_preflight_summary_passes_schema_three_pair(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert "- Protocol: budgeted-context-protocol-v4" in summary
    assert "| baseline | 1 | 1/1 | 100 | 10 | 0 | 0/0 |" in summary
    assert "| projection | 1 | 1/1 | 90 | 10 | 1 | 0/0 |" in summary
    assert "- Protocol snapshot: pass" in summary
    assert "- Orchestration evidence: pass" in summary
    assert "- Preflight gate: PASS" in summary


def test_budgeted_formal_summary_passes_complete_orchestration_evidence(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "| case_a | baseline | 3 | 3/3 | 300 | 30 | 0/0/0 |" in summary
    assert "| case_a | projection | 3 | 3/3 | 270 | 30 | 0/0/0 |" in summary
    assert "- Provider input Token budget: 570/270000 (pass)" in summary
    assert "- Provider output Token budget: 60/30000 (pass)" in summary
    assert "- Orchestration evidence: pass" in summary
    assert "- Advancement gate: PASS" in summary


def test_formal_archive_reproduces_real_formal_summary(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    archive_root = tmp_path / "archive"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)
    source_summary = summarize_context_experiment_results(
        results_root,
        protocol_path,
    )

    archived = archive_formal_experiment(
        source_root=results_root,
        archive_root=archive_root,
        protocol_path=protocol_path,
    )

    assert archived.summary == source_summary
    assert summarize_context_experiment_results(archive_root, protocol_path) == (
        source_summary
    )
    assert (archive_root / "REPORT.md").read_text(encoding="utf-8") == (
        f"{source_summary}\n"
    )
    assert (archive_root / "ARCHIVE_MANIFEST.json").is_file()


def test_budgeted_formal_summary_fails_tampered_event_usage(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)
    event_path = results_root / "formal-events.jsonl"
    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    events[1]["cumulative_input_tokens"] = 999
    event_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Orchestration evidence: fail" in summary
    assert "- Advancement gate: FAIL" in summary


def test_budgeted_formal_summary_fails_results_swapped_between_slots(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)
    baseline_path = (
        results_root / "01-case_a-baseline" / "result.json"
    )
    projection_path = (
        results_root / "02-case_a-projection" / "result.json"
    )
    baseline = baseline_path.read_text(encoding="utf-8")
    projection = projection_path.read_text(encoding="utf-8")
    baseline_path.write_text(projection, encoding="utf-8")
    projection_path.write_text(baseline, encoding="utf-8")

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Orchestration evidence: fail" in summary
    assert "- Advancement gate: FAIL" in summary


def test_budgeted_formal_summary_fails_provider_budget_gate(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path, formal_input_budget=550)
    _write_budgeted_formal_results(results_root, protocol_path)

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Provider input Token budget: 570/550 (fail)" in summary
    assert "- Orchestration evidence: pass" in summary
    assert "- Advancement gate: FAIL" in summary


def test_budgeted_formal_summary_rejects_tampered_plan(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)
    plan_path = results_root / "formal-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["runs"][0]["arm"] = "projection"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ValueError, match="Formal plan disagrees"):
        summarize_context_experiment_results(results_root, protocol_path)


def test_budgeted_formal_summary_fails_tampered_protocol_snapshot(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_formal_results(results_root, protocol_path)
    snapshot_path = results_root / "protocol.snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["protocol_id"] = "tampered-after-run"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Orchestration evidence: fail" in summary
    assert "- Advancement gate: FAIL" in summary


def test_budgeted_preflight_reports_incomplete_event_sequence(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)
    event_path = results_root / "preflight-events.jsonl"
    lines = event_path.read_text(encoding="utf-8").splitlines()
    event_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert "- Orchestration evidence: fail" in summary
    assert "- Preflight gate: FAIL" in summary


def test_budgeted_preflight_reports_results_swapped_between_slots(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)
    baseline_path = results_root / "01-baseline" / "result.json"
    projection_path = results_root / "02-projection" / "result.json"
    baseline = baseline_path.read_text(encoding="utf-8")
    projection = projection_path.read_text(encoding="utf-8")
    baseline_path.write_text(projection, encoding="utf-8")
    projection_path.write_text(baseline, encoding="utf-8")

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert "- Orchestration evidence: fail" in summary
    assert "- Preflight gate: FAIL" in summary


def test_budgeted_preflight_rejects_tampered_frozen_plan(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)
    plan_path = results_root / "preflight-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["runs"][0]["arm"] = "projection"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ValueError, match="plan disagrees"):
        summarize_context_preflight_results(results_root, protocol_path)


def test_budgeted_context_preflight_rejects_projection_configuration_drift(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)
    result_path = results_root / "02-projection" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    experiment = result["context_experiment"]
    experiment["max_request_bytes"] = 11_000
    experiment["trace_configuration"]["max_request_bytes"] = 11_000
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="projection result does not match the registered budgeted arm",
    ):
        summarize_context_preflight_results(results_root, protocol_path)


def test_budgeted_context_preflight_fails_changed_protocol_snapshot(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)
    (results_root / "protocol.snapshot.json").write_text("{}", encoding="utf-8")

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert "- Protocol snapshot: fail" in summary
    assert "- Preflight gate: FAIL" in summary


def test_context_preflight_cli_accepts_budgeted_v4_protocol(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_budgeted_context_protocol(protocol_path)
    _write_budgeted_preflight_results(results_root, protocol_path)

    exit_code = main(
        (
            str(results_root),
            "--context-preflight-protocol",
            str(protocol_path),
        )
    )

    assert exit_code == 0
    assert "- Preflight gate: PASS" in capsys.readouterr().out


def test_context_preflight_cli_selects_preflight_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)

    exit_code = main(
        (
            str(results_root),
            "--context-preflight-protocol",
            str(protocol_path),
        )
    )

    assert exit_code == 0
    assert "- Preflight gate: PASS" in capsys.readouterr().out


def test_context_preflight_cli_returns_failure_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(
        results_root,
        protocol_path,
        arms=("baseline",),
        input_tokens=(100,),
    )

    exit_code = main(
        (
            str(results_root),
            "--context-preflight-protocol",
            str(protocol_path),
        )
    )

    assert exit_code == 1
    assert "- Preflight gate: FAIL" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("arms", "projection_changes", "failed_readbacks", "input_tokens", "failure"),
    (
        (("baseline",), 1, 0, (100,), "- Run shape: fail"),
        (
            ("baseline", "baseline"),
            1,
            0,
            (100, 100),
            "- Run shape: fail",
        ),
        (
            ("baseline", "projection"),
            0,
            0,
            (100, 90),
            "- Projection activity: 0/1 (fail)",
        ),
        (
            ("baseline", "projection"),
            1,
            1,
            (100, 90),
            "- Failed or cancelled readbacks: 1/0 (fail)",
        ),
        (
            ("baseline", "projection"),
            1,
            0,
            (200, 200),
            "- Provider input Token budget: 400/300 (fail)",
        ),
    ),
)
def test_context_preflight_summary_reports_gate_failures(
    tmp_path: Path,
    arms: tuple[str, ...],
    projection_changes: int,
    failed_readbacks: int,
    input_tokens: tuple[int, ...],
    failure: str,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(
        results_root,
        protocol_path,
        arms=arms,
        projection_changes=projection_changes,
        failed_readbacks=failed_readbacks,
        input_tokens=input_tokens,
    )

    summary = summarize_context_preflight_results(results_root, protocol_path)

    assert failure in summary
    assert "- Preflight gate: FAIL" in summary


def test_context_preflight_summary_rejects_missing_provider_usage(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)
    result_path = results_root / "case_a-baseline-0" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    del result["run"]["input_tokens"]
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(TypeError, match="input_tokens must be an integer"):
        summarize_context_preflight_results(results_root, protocol_path)


def test_context_preflight_summary_rejects_tampered_artifact(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)
    (results_root / "case_a-projection-1" / "workspace.patch").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        summarize_context_preflight_results(results_root, protocol_path)


def test_context_preflight_summary_rejects_mixed_model(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)
    result_path = results_root / "case_a-projection-1" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["model"] = "another-model"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="result model does not match context protocol",
    ):
        summarize_context_preflight_results(results_root, protocol_path)


def test_context_preflight_summary_rejects_dirty_minicode_run(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    _write_context_protocol(protocol_path, schema_version=2)
    _write_preflight_results(results_root, protocol_path)
    result_path = results_root / "case_a-projection-1" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["minicode_dirty"] = True
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="context experiment contains a dirty MiniCode run",
    ):
        summarize_context_preflight_results(results_root, protocol_path)


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
    assert "- Task Outcome: baseline 2/2, projection 2/2" in summary
    assert "- Operational/Budget: baseline 2/2, projection 2/2" in summary
    assert "- Trace Compliance: baseline 2/2, projection 2/2" in summary
    assert (
        "- Safe Task Success (frozen composite): baseline 2/2, projection 2/2 (pass)"
    ) in summary
    assert "- Aggregate input Token reduction: 15.0% (pass)" in summary
    assert "- Failed or cancelled readbacks: 0 (pass)" in summary
    assert "- Advancement gate: PASS" in summary


def test_context_summary_separates_outcome_operation_and_trace(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)

    for arm, trace_passed, input_tokens in (
        ("baseline", False, 100),
        ("projection", True, 90),
    ):
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
                "trace_passed": trace_passed,
                "passed": trace_passed,
            },
            directory_name=f"case_a-{arm}",
            run_id=f"run_{arm}",
            context_experiment=_context_experiment(
                arm,
                protocol_id="context-protocol-v2",
            ),
            trace_evaluation={
                "missing_required_tools": (["list_files"] if arm == "baseline" else []),
                "requested_forbidden_tools": [],
                "successful_test_after_last_change": True,
            },
            case_manifest=_schema_3_case_manifest(),
        )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Task Outcome: baseline 1/1, projection 1/1" in summary
    assert "- Operational/Budget: baseline 1/1, projection 1/1" in summary
    assert "- Trace Compliance: baseline 0/1, projection 1/1" in summary
    assert "- Process Coverage (diagnostic): baseline 0/1, projection 1/1" in summary
    assert (
        "- Trace Safety (forbidden requests + post-change test): "
        "baseline 1/1, projection 1/1"
    ) in summary
    assert (
        "- Candidate v5 Safe Task Success (not a gate): baseline 1/1, projection 1/1"
    ) in summary
    assert (
        "- Safe Task Success (frozen composite): baseline 0/1, projection 1/1 (fail)"
    ) in summary
    assert "- Advancement gate: FAIL" in summary


@pytest.mark.parametrize(
    "projection_trace_evaluation",
    (
        {
            "missing_required_tools": [],
            "requested_forbidden_tools": ["create_file"],
            "successful_test_after_last_change": True,
        },
        {
            "missing_required_tools": ["run_tests"],
            "requested_forbidden_tools": [],
            "successful_test_after_last_change": False,
        },
    ),
)
def test_context_summary_separates_trace_safety_failures(
    tmp_path: Path,
    projection_trace_evaluation: dict[str, object],
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)

    for arm, input_tokens in (("baseline", 100), ("projection", 90)):
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
                "trace_passed": arm == "baseline",
                "passed": arm == "baseline",
            },
            directory_name=f"case_a-{arm}",
            run_id=f"run_{arm}",
            context_experiment=_context_experiment(
                arm,
                protocol_id="context-protocol-v2",
            ),
            trace_evaluation=(
                projection_trace_evaluation
                if arm == "projection"
                else {
                    "missing_required_tools": [],
                    "requested_forbidden_tools": [],
                    "successful_test_after_last_change": True,
                }
            ),
        )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    expected_projection_coverage = (
        "0/1" if projection_trace_evaluation["missing_required_tools"] else "1/1"
    )
    assert (
        "- Process Coverage (diagnostic): baseline 1/1, projection "
        f"{expected_projection_coverage}"
    ) in summary
    assert (
        "- Trace Safety (forbidden requests + post-change test): "
        "baseline 1/1, projection 0/1"
    ) in summary
    assert (
        "- Candidate v5 Safe Task Success (not a gate): baseline 1/1, projection 0/1"
    ) in summary
    assert (
        "- Safe Task Success (frozen composite): baseline 1/1, projection 0/1 (fail)"
    ) in summary


def test_context_summary_rejects_trace_details_that_disagree_with_verdict(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)
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
        directory_name="case_a-baseline",
        run_id="run_baseline",
        context_experiment=_context_experiment(
            "baseline",
            protocol_id="context-protocol-v2",
        ),
        trace_evaluation={
            "missing_required_tools": ["list_files"],
            "requested_forbidden_tools": [],
            "successful_test_after_last_change": True,
        },
    )

    with pytest.raises(ValueError, match="trace details disagree with verdict"):
        summarize_context_experiment_results(results_root, protocol_path)


@pytest.mark.parametrize(
    ("trace_evaluation", "case_manifest", "trace_passed", "error"),
    (
        (
            {
                "missing_required_tools": ["edit_file"],
                "requested_forbidden_tools": [],
                "successful_test_after_last_change": True,
            },
            _schema_3_case_manifest(),
            False,
            "missing process tools are not declared",
        ),
        (
            {
                "missing_required_tools": [],
                "requested_forbidden_tools": ["read_file"],
                "successful_test_after_last_change": True,
            },
            _schema_3_case_manifest(),
            False,
            "requested forbidden tools are not declared",
        ),
        (
            {
                "missing_required_tools": [],
                "requested_forbidden_tools": [],
                "successful_test_after_last_change": True,
            },
            _schema_3_case_manifest(
                require_successful_test_after_change=False,
            ),
            True,
            "post-change test result exists",
        ),
    ),
)
def test_context_summary_rejects_trace_details_outside_schema_3_contract(
    tmp_path: Path,
    trace_evaluation: dict[str, object],
    case_manifest: dict[str, object],
    trace_passed: bool,
    error: str,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)
    _write_result(
        results_root,
        case_id="case_a",
        accepted=True,
        model_calls=1,
        tool_executions=1,
        input_tokens=100,
        output_tokens=10,
        workspace_changes=["M implementation.py"],
        schema_version=2,
        verdict={
            "outcome_passed": True,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": trace_passed,
            "passed": trace_passed,
        },
        directory_name="case_a-baseline",
        run_id="run_baseline",
        context_experiment=_context_experiment(
            "baseline",
            protocol_id="context-protocol-v2",
        ),
        trace_evaluation=trace_evaluation,
        case_manifest=case_manifest,
    )

    with pytest.raises(ValueError, match=error):
        summarize_context_experiment_results(results_root, protocol_path)


def test_context_summary_accepts_v2_adaptive_configuration(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)

    for arm, tokens in (("baseline", 100), ("projection", 90)):
        _write_result(
            results_root,
            case_id="case_a",
            accepted=True,
            model_calls=1,
            tool_executions=1,
            input_tokens=tokens,
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
            directory_name=f"case_a-{arm}",
            run_id=f"run_{arm}",
            context_experiment=_context_experiment(
                arm,
                protocol_id="context-protocol-v2",
            ),
        )

    summary = summarize_context_experiment_results(results_root, protocol_path)

    assert "- Protocol: context-protocol-v2" in summary
    assert "- Advancement gate: PASS" in summary


def test_context_summary_rejects_v2_result_with_another_loading_mode(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)
    context_experiment = _context_experiment(
        "projection",
        protocol_id="context-protocol-v2",
    )
    trace_configuration = context_experiment["trace_configuration"]
    assert isinstance(trace_configuration, dict)
    trace_configuration["retrieval_tool_loading"] = "eager"
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
        run_id="run_projection",
        context_experiment=context_experiment,
    )

    with pytest.raises(
        ValueError,
        match="context trace retrieval-tool loading disagrees",
    ):
        summarize_context_experiment_results(results_root, protocol_path)


def test_context_summary_rejects_incomplete_v2_protocol(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    results_root = tmp_path / "formal"
    results_root.mkdir()
    _write_context_protocol(protocol_path, repetitions=1, schema_version=2)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    del protocol["arms"]["projection"]["minimum_net_savings_bytes"]
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="context protocol arm configuration is missing minimum_net_savings_bytes",
    ):
        summarize_context_experiment_results(results_root, protocol_path)


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
    assert "- Task Outcome: baseline 2/2, projection 1/2" in summary
    assert "- Operational/Budget: baseline 2/2, projection 1/2" in summary
    assert "- Trace Compliance: baseline 2/2, projection 1/2" in summary
    assert (
        "- Safe Task Success (frozen composite): baseline 2/2, projection 1/2 (fail)"
    ) in summary
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
