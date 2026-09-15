from collections.abc import Sequence
from pathlib import Path

import pytest

from minicode import cli
from minicode.evaluation_run import EvaluationArm, context_threshold_for_arm, main


def test_evaluation_run_uses_case_task_and_budget(
    monkeypatch,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )
    received_calls: list[tuple[tuple[str, ...], int | None]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
    ) -> int:
        assert arguments is not None
        received_calls.append(
            (tuple(arguments), max_inline_tool_result_bytes),
        )
        return 17

    monkeypatch.setattr(
        cli,
        "main",
        record_cli_call,
    )

    exit_code = main(
        [
            "--case-root",
            str(case_root),
        ]
    )

    assert exit_code == 17
    assert received_calls == [
        (
            (
                "run",
                (case_root / "task.txt").read_text(encoding="utf-8").strip(),
                "--max-turns",
                "8",
                "--max-tool-calls",
                "8",
                "--trace",
            ),
            None,
        )
    ]


def test_evaluation_run_passes_projection_arm_to_python_cli(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )
    received_thresholds: list[int | None] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
    ) -> int:
        assert arguments is not None
        received_thresholds.append(max_inline_tool_result_bytes)
        return 0

    monkeypatch.setattr(cli, "main", record_cli_call)

    assert main(["--case-root", str(case_root), "--arm", "projection"]) == 0
    assert received_thresholds == [500]


def test_context_threshold_for_arm_keeps_baseline_disabled() -> None:
    assert context_threshold_for_arm(EvaluationArm.BASELINE) is None
    assert context_threshold_for_arm(EvaluationArm.PROJECTION) == 500


def test_evaluation_run_rejects_unknown_arm_before_cli(monkeypatch) -> None:
    def unexpected_cli_call(*args, **kwargs):
        pytest.fail("invalid arm must be rejected before the coding CLI")

    monkeypatch.setattr(cli, "main", unexpected_cli_call)

    with pytest.raises(SystemExit) as exc_info:
        main(["--case-root", ".", "--arm", "unknown"])

    assert exc_info.value.code == 2
