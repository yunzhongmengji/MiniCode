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
    received_calls: list[tuple[tuple[str, ...], int | None, object, object]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
    ) -> int:
        assert arguments is not None
        received_calls.append(
            (
                tuple(arguments),
                max_inline_tool_result_bytes,
                budgeted_context_configuration,
                expected_model,
            ),
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
            None,
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
        budgeted_context_configuration,
        expected_model,
    ) -> int:
        assert arguments is not None
        assert budgeted_context_configuration is None
        assert expected_model is None
        received_thresholds.append(max_inline_tool_result_bytes)
        return 0

    monkeypatch.setattr(cli, "main", record_cli_call)

    assert main(["--case-root", str(case_root), "--arm", "projection"]) == 0
    assert received_thresholds == [500]


@pytest.mark.parametrize("arm", (EvaluationArm.BASELINE, EvaluationArm.PROJECTION))
def test_evaluation_run_resolves_registered_v4_arm_from_protocol(
    monkeypatch,
    arm: EvaluationArm,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root
        / "benchmarks"
        / "coding_agent"
        / "cases"
        / "large_search_context_recall"
    )
    protocol_path = (
        project_root
        / "benchmarks"
        / "context_projection"
        / "real_model_protocol_v4.json"
    )
    received: list[tuple[int | None, object, object]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
    ) -> int:
        assert arguments is not None
        received.append(
            (
                max_inline_tool_result_bytes,
                budgeted_context_configuration,
                expected_model,
            )
        )
        return 0

    monkeypatch.setattr(cli, "main", record_cli_call)

    assert (
        main(
            [
                "--case-root",
                str(case_root),
                "--context-protocol",
                str(protocol_path),
                "--arm",
                arm,
            ]
        )
        == 0
    )
    assert received[0][0] is None
    assert received[0][2] == "qwen3.7-flash-2026-07-15"

    if arm is EvaluationArm.BASELINE:
        assert received[0][1] is None
    else:
        configuration = received[0][1]
        assert configuration.max_request_bytes == 10_000
        assert configuration.protected_recent_batch_count == 2


def test_evaluation_run_requires_explicit_arm_with_registered_protocol() -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root
        / "benchmarks"
        / "coding_agent"
        / "cases"
        / "large_search_context_recall"
    )
    protocol_path = (
        project_root
        / "benchmarks"
        / "context_projection"
        / "real_model_protocol_v4.json"
    )

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--case-root",
                str(case_root),
                "--context-protocol",
                str(protocol_path),
            ]
        )

    assert exc_info.value.code == 2


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
