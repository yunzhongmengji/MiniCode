import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from minicode.evaluation_case import EvaluationBudget
from minicode.evaluation_result import (
    build_evaluation_verdict,
    parse_trace,
    record_result,
    summarize_context_experiment,
    summarize_trace,
)
from minicode.evaluation_run import EvaluationArm
from minicode.evaluation_trace import TraceEvaluation

_TRACE = """Trace run_001
001 run_started {"initial_history_items": 1}
002 model_call_started {"context_profile": {"total_bytes": 100}, "context_projection": {"changed_tool_result_count": 0, "max_inline_tool_result_bytes": null, "strategy": "identity", "total_bytes_after": 100, "total_bytes_before": 100, "total_bytes_saved": 0}, "turn": 1}
003 model_call_finished {"input_tokens": 12, "outcome": "succeeded", "output_tokens": 5, "tool_call_count": 1, "turn": 1}
004 tool_policy_decided {"call_id": "call_001", "outcome": "allow", "reason": "read", "tool_name": "read_file"}
005 tool_execution_started {"call_id": "call_001", "tool_name": "read_file"}
006 tool_execution_finished {"call_id": "call_001", "outcome": "succeeded", "tool_name": "read_file"}
007 run_finished {"outcome": "succeeded", "stop_reason": "completed", "turns_used": 1}
"""

_PROJECTION_TRACE = """Trace run_002
001 run_started {"initial_history_items": 1}
002 model_call_started {"context_profile": {"total_bytes": 90}, "context_projection": {"changed_tool_result_count": 0, "max_inline_tool_result_bytes": 500, "strategy": "tool_result_reference", "total_bytes_after": 90, "total_bytes_before": 90, "total_bytes_saved": 0}, "turn": 1}
003 model_call_finished {"input_tokens": 20, "outcome": "succeeded", "output_tokens": 2, "tool_call_count": 1, "turn": 1}
004 tool_policy_decided {"call_id": "call_restore", "outcome": "allow", "reason": "read", "tool_name": "read_tool_result"}
005 tool_execution_started {"call_id": "call_restore", "tool_name": "read_tool_result"}
006 tool_execution_finished {"call_id": "call_restore", "outcome": "succeeded", "tool_name": "read_tool_result"}
007 model_call_started {"context_profile": {"total_bytes": 60}, "context_projection": {"changed_tool_result_count": 1, "max_inline_tool_result_bytes": 500, "strategy": "tool_result_reference", "total_bytes_after": 60, "total_bytes_before": 160, "total_bytes_saved": 100}, "turn": 2}
008 model_call_finished {"input_tokens": 15, "outcome": "succeeded", "output_tokens": 3, "tool_call_count": 0, "turn": 2}
009 run_finished {"outcome": "succeeded", "stop_reason": "completed", "turns_used": 2}
"""


def _initialize_repository(path: Path) -> None:
    subprocess.run(
        ("git", "init", "-q"),
        cwd=path,
        check=True,
    )
    (path / ".gitignore").write_text(
        "__pycache__/\n",
        encoding="utf-8",
    )
    subprocess.run(
        ("git", "add", "."),
        cwd=path,
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=MiniCode Test",
            "-c",
            "user.email=minicode@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
        cwd=path,
        check=True,
    )


def test_trace_parser_reuses_validated_replay_summary() -> None:
    replay = parse_trace(_TRACE)

    assert summarize_trace(replay) == {
        "run_id": "run_001",
        "outcome": "succeeded",
        "stop_reason": "completed",
        "turns_used": 1,
        "model_call_count": 1,
        "tool_execution_count": 1,
        "input_tokens": 12,
        "output_tokens": 5,
        "tool_requests": {
            "read_file": 1,
        },
    }


def test_context_experiment_summary_validates_trace_configuration() -> None:
    summary = summarize_context_experiment(
        parse_trace(_TRACE),
        protocol_id="context-projection-real-model-pilot-v1",
        arm=EvaluationArm.BASELINE,
    )

    assert summary == {
        "protocol_id": "context-projection-real-model-pilot-v1",
        "arm": "baseline",
        "max_inline_tool_result_bytes": None,
        "trace_configuration": {
            "strategy": "identity",
            "max_inline_tool_result_bytes": None,
        },
        "metrics": {
            "model_call_count": 1,
            "model_visible_bytes": 100,
            "canonical_bytes": 100,
            "projection_bytes_saved": 0,
            "changed_tool_result_count": 0,
            "successful_readback_count": 0,
            "failed_readback_count": 0,
            "cancelled_readback_count": 0,
        },
    }


def test_context_experiment_summary_rejects_declared_arm_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="declared context arm projection disagrees with Trace",
    ):
        summarize_context_experiment(
            parse_trace(_TRACE),
            protocol_id="context-projection-real-model-pilot-v1",
            arm=EvaluationArm.PROJECTION,
        )


def test_context_experiment_summary_aggregates_projection_and_readback() -> None:
    summary = summarize_context_experiment(
        parse_trace(_PROJECTION_TRACE),
        protocol_id="context-projection-real-model-pilot-v1",
        arm=EvaluationArm.PROJECTION,
    )

    assert summary["max_inline_tool_result_bytes"] == 500
    assert summary["trace_configuration"] == {
        "strategy": "tool_result_reference",
        "max_inline_tool_result_bytes": 500,
    }
    assert summary["metrics"] == {
        "model_call_count": 2,
        "model_visible_bytes": 150,
        "canonical_bytes": 250,
        "projection_bytes_saved": 100,
        "changed_tool_result_count": 1,
        "successful_readback_count": 1,
        "failed_readback_count": 0,
        "cancelled_readback_count": 0,
    }


def test_verdict_separates_accepted_result_from_operational_failure() -> None:
    verdict = build_evaluation_verdict(
        replay=parse_trace(_TRACE),
        acceptance_exit_code=0,
        agent_exit_code=1,
        budget=EvaluationBudget(
            max_turns=1,
            max_tool_calls=1,
        ),
        trace_evaluation=TraceEvaluation(
            missing_required_tools=(),
            requested_forbidden_tools=(),
        ),
    )

    assert verdict == {
        "outcome_passed": True,
        "operational_passed": False,
        "budget_passed": True,
        "trace_passed": True,
        "passed": False,
    }


def test_verdict_reports_a_run_over_its_turn_budget() -> None:
    replay = parse_trace(
        _TRACE.replace(
            '"turns_used": 1',
            '"turns_used": 2',
        )
    )

    assert build_evaluation_verdict(
        replay=replay,
        acceptance_exit_code=0,
        agent_exit_code=0,
        budget=EvaluationBudget(
            max_turns=1,
            max_tool_calls=1,
        ),
        trace_evaluation=TraceEvaluation(
            missing_required_tools=(),
            requested_forbidden_tools=(),
        ),
    ) == {
        "outcome_passed": True,
        "operational_passed": True,
        "budget_passed": False,
        "trace_passed": True,
        "passed": False,
    }


def test_verdict_fails_when_trace_contract_is_not_satisfied() -> None:
    assert build_evaluation_verdict(
        replay=parse_trace(_TRACE),
        acceptance_exit_code=0,
        agent_exit_code=0,
        budget=EvaluationBudget(
            max_turns=1,
            max_tool_calls=1,
        ),
        trace_evaluation=TraceEvaluation(
            missing_required_tools=("run_tests",),
            requested_forbidden_tools=(),
        ),
    ) == {
        "outcome_passed": True,
        "operational_passed": True,
        "budget_passed": True,
        "trace_passed": False,
        "passed": False,
    }


@pytest.mark.parametrize(
    ("acceptance_source", "expected_accepted"),
    (
        (
            "print('PASS fixture')\n",
            True,
        ),
        (
            "raise SystemExit('simulated rejection')\n",
            False,
        ),
    ),
)
def test_result_recorder_preserves_success_and_failure_results(
    tmp_path: Path,
    acceptance_source: str,
    expected_accepted: bool,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    (case_root / "case.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "case_id": "case",
                "category": "fixture",
                "ground_truth": {
                    "defined_by": "test",
                    "evidence": [
                        "acceptance.py",
                    ],
                },
                "allowed_changes": [],
                "forbidden_actions": [],
                "trace_expectations": {
                    "required_successful_tools": ["read_file"],
                    "forbidden_tool_requests": ["edit_file"],
                },
                "budget": {
                    "max_turns": 1,
                    "max_tool_calls": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    (case_root / "acceptance.py").write_text(
        acceptance_source,
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    implementation_path = workspace / "implementation.py"
    implementation_path.write_text(
        "VALUE = 'before'\n",
        encoding="utf-8",
    )
    _initialize_repository(workspace)
    implementation_path.write_text(
        "VALUE = 'after'\n",
        encoding="utf-8",
    )
    (workspace / "created.py").write_text(
        "CREATED = True\n",
        encoding="utf-8",
    )
    result_directory = tmp_path / "result"
    result_directory.mkdir()
    answer_path = result_directory / "answer.txt"
    trace_path = result_directory / "trace.txt"
    output_path = result_directory / "result.json"
    answer_path.write_text(
        "Completed.",
        encoding="utf-8",
    )
    trace_path.write_text(
        _TRACE,
        encoding="utf-8",
    )

    accepted = record_result(
        case_root=case_root,
        workspace=workspace,
        answer_path=answer_path,
        trace_path=trace_path,
        output_path=output_path,
        model="test-model",
        agent_exit_code=0,
        context_protocol_id="context-projection-real-model-pilot-v1",
        context_arm=EvaluationArm.BASELINE,
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert accepted is expected_accepted
    assert result["schema_version"] == 2
    assert result["accepted"] is expected_accepted
    assert result["verdict"] == {
        "outcome_passed": expected_accepted,
        "operational_passed": True,
        "budget_passed": True,
        "trace_passed": True,
        "passed": expected_accepted,
    }
    assert result["acceptance"]["exit_code"] == (0 if expected_accepted else 1)
    assert result["case_id"] == "case"
    assert result["case_manifest"]["ground_truth"] == {
        "defined_by": "test",
        "evidence": [
            "acceptance.py",
        ],
    }
    assert result["case_manifest"]["budget"] == {
        "max_turns": 1,
        "max_tool_calls": 1,
    }
    assert result["case_manifest"]["trace_expectations"] == {
        "required_successful_tools": ["read_file"],
        "forbidden_tool_requests": ["edit_file"],
    }
    assert result["trace_evaluation"] == {
        "missing_required_tools": [],
        "requested_forbidden_tools": [],
        "successful_test_after_last_change": None,
    }
    assert result["model"] == "test-model"
    assert result["context_experiment"]["protocol_id"] == (
        "context-projection-real-model-pilot-v1"
    )
    assert result["context_experiment"]["arm"] == "baseline"
    assert result["context_experiment"]["metrics"]["model_visible_bytes"] == 100
    assert result["run"]["input_tokens"] == 12
    assert result["artifacts"]["answer"]["sha256"]
    assert result["artifacts"]["trace"]["sha256"]
    patch_path = result_directory / "workspace.patch"
    patch = patch_path.read_text(encoding="utf-8")
    assert "-VALUE = 'before'" in patch
    assert "+VALUE = 'after'" in patch
    assert "new file mode" in patch
    assert "+CREATED = True" in patch
    assert result["artifacts"]["workspace_patch"] == {
        "file": "workspace.patch",
        "sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
    }

    replay_workspace = tmp_path / "replay-workspace"
    replay_workspace.mkdir()
    replayed_implementation = replay_workspace / "implementation.py"
    replayed_implementation.write_text(
        "VALUE = 'before'\n",
        encoding="utf-8",
    )
    _initialize_repository(replay_workspace)
    subprocess.run(
        (
            "git",
            "apply",
            str(patch_path),
        ),
        cwd=replay_workspace,
        check=True,
    )
    assert (
        replayed_implementation.read_text(
            encoding="utf-8",
        )
        == "VALUE = 'after'\n"
    )
    assert (replay_workspace / "created.py").read_text(
        encoding="utf-8",
    ) == "CREATED = True\n"

    with pytest.raises(FileExistsError):
        record_result(
            case_root=case_root,
            workspace=workspace,
            answer_path=answer_path,
            trace_path=trace_path,
            output_path=output_path,
            model="test-model",
            agent_exit_code=0,
        )
