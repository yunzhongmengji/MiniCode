import json
from pathlib import Path

import pytest

from minicode.evaluation_summary import summarize_results


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
) -> None:
    case_root = root / case_id
    case_root.mkdir()
    result = {
        "schema_version": 1,
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
    (case_root / "result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
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
    )
    _write_result(
        tmp_path,
        case_id="case_b",
        accepted=False,
        model_calls=1,
        tool_executions=0,
        input_tokens=40,
        output_tokens=10,
        workspace_changes=[],
    )

    summary = summarize_results(tmp_path)

    assert "| case_a | yes | 2 | 3 | 100 | 20 | 1 |" in summary
    assert "| case_b | no | 1 | 0 | 40 | 10 | 0 |" in summary
    assert "- Accepted: 1/2 (50.0%)" in summary
    assert "- Total model calls: 3" in summary
    assert "- Total tool executions: 3" in summary
    assert "- Total input tokens: 140" in summary
    assert "- Total output tokens: 30" in summary
    assert "- Models: test-model" in summary
    assert "- MiniCode commits: 1234567" in summary


def test_summary_rejects_directory_without_results(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="no result.json files found",
    ):
        summarize_results(tmp_path)
