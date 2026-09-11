import json
import subprocess
from pathlib import Path

import pytest

from minicode.evaluation_case import EvaluationBudget
from minicode.evaluation_result import (
    build_evaluation_verdict,
    parse_trace,
    record_result,
    summarize_trace,
)

_TRACE = """Trace run_001
001 run_started {"initial_history_items": 1}
002 model_call_started {"turn": 1}
003 model_call_finished {"input_tokens": 12, "outcome": "succeeded", "output_tokens": 5, "tool_call_count": 1, "turn": 1}
004 tool_policy_decided {"call_id": "call_001", "outcome": "allow", "reason": "read", "tool_name": "read_file"}
005 tool_execution_started {"call_id": "call_001", "tool_name": "read_file"}
006 tool_execution_finished {"call_id": "call_001", "outcome": "succeeded", "tool_name": "read_file"}
007 run_finished {"outcome": "succeeded", "stop_reason": "completed", "turns_used": 1}
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


def test_verdict_separates_accepted_result_from_operational_failure() -> None:
    verdict = build_evaluation_verdict(
        replay=parse_trace(_TRACE),
        acceptance_exit_code=0,
        agent_exit_code=1,
        budget=EvaluationBudget(
            max_turns=1,
            max_tool_calls=1,
        ),
    )

    assert verdict == {
        "outcome_passed": True,
        "operational_passed": False,
        "budget_passed": True,
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
    ) == {
        "outcome_passed": True,
        "operational_passed": True,
        "budget_passed": False,
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
                "schema_version": 1,
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
    _initialize_repository(workspace)
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
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert accepted is expected_accepted
    assert result["accepted"] is expected_accepted
    assert result["verdict"] == {
        "outcome_passed": expected_accepted,
        "operational_passed": True,
        "budget_passed": True,
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
    assert result["model"] == "test-model"
    assert result["run"]["input_tokens"] == 12
    assert result["artifacts"]["answer"]["sha256"]
    assert result["artifacts"]["trace"]["sha256"]

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
