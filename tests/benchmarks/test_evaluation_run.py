from collections.abc import Sequence
from pathlib import Path

from minicode import cli
from minicode.evaluation_run import main


def test_evaluation_run_uses_case_task_and_budget(
    monkeypatch,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )
    received_arguments: list[tuple[str, ...]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
    ) -> int:
        assert arguments is not None
        received_arguments.append(
            tuple(arguments),
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
    assert received_arguments == [
        (
            "run",
            (case_root / "task.txt").read_text(encoding="utf-8").strip(),
            "--max-turns",
            "8",
            "--max-tool-calls",
            "8",
            "--trace",
        )
    ]
