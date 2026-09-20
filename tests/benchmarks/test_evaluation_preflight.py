from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import minicode.evaluation_preflight_executor as executor_module
import minicode.evaluation_summary as summary_module
from minicode.evaluation_preflight import (
    PreflightRunRequest,
    main,
    run_budgeted_context_preflight,
)

PROTOCOL_PATH = Path("benchmarks/context_projection/real_model_protocol_v4.json")


class _RecordingExecutor:
    def __init__(
        self,
        *,
        outcomes: tuple[bool, ...],
        record_result: bool = True,
    ) -> None:
        self._outcomes = iter(outcomes)
        self._record_result = record_result
        self.requests: list[PreflightRunRequest] = []

    def execute(self, request: PreflightRunRequest) -> bool:
        self.requests.append(request)

        if self._record_result:
            (request.result_directory / "result.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

        return next(self._outcomes)


def _read_events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_preflight_runs_registered_arms_in_order(tmp_path: Path) -> None:
    executor = _RecordingExecutor(outcomes=(True, True))
    results_root = tmp_path / "preflight"

    result = run_budgeted_context_preflight(
        protocol_path=PROTOCOL_PATH,
        results_root=results_root,
        executor=executor,
    )

    assert result.passed
    assert not result.stopped_early
    assert [request.arm for request in executor.requests] == [
        "baseline",
        "projection",
    ]
    assert [request.run_index for request in executor.requests] == [1, 2]
    assert (results_root / "protocol.snapshot.json").read_bytes() == (
        PROTOCOL_PATH.read_bytes()
    )

    plan = json.loads(
        (results_root / "preflight-plan.json").read_text(encoding="utf-8")
    )
    assert plan["case_id"] == "large_search_context_recall"
    assert plan["runs"] == [
        {
            "arm": "baseline",
            "result_directory": "01-baseline",
            "run_index": 1,
        },
        {
            "arm": "projection",
            "result_directory": "02-projection",
            "run_index": 2,
        },
    ]
    assert [event["event"] for event in _read_events(
        results_root / "preflight-events.jsonl"
    )] == [
        "run_started",
        "run_finished",
        "run_started",
        "run_finished",
    ]


def test_preflight_stops_before_projection_when_baseline_fails(
    tmp_path: Path,
) -> None:
    executor = _RecordingExecutor(outcomes=(False, True))
    results_root = tmp_path / "preflight"

    result = run_budgeted_context_preflight(
        protocol_path=PROTOCOL_PATH,
        results_root=results_root,
        executor=executor,
    )

    assert not result.passed
    assert result.stopped_early
    assert [request.arm for request in executor.requests] == ["baseline"]
    assert result.records[0].failure_reason == "executor_reported_failure"
    assert not (results_root / "02-projection").exists()


def test_preflight_rejects_success_without_recorded_result(tmp_path: Path) -> None:
    executor = _RecordingExecutor(outcomes=(True,), record_result=False)

    result = run_budgeted_context_preflight(
        protocol_path=PROTOCOL_PATH,
        results_root=tmp_path / "preflight",
        executor=executor,
    )

    assert not result.passed
    assert result.stopped_early
    assert result.records[0].failure_reason == "result_json_missing"
    assert not result.records[0].result_recorded


def test_preflight_never_reuses_an_existing_results_root(tmp_path: Path) -> None:
    results_root = tmp_path / "preflight"
    results_root.mkdir()
    sentinel = results_root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    executor = _RecordingExecutor(outcomes=(True, True))

    with pytest.raises(FileExistsError):
        run_budgeted_context_preflight(
            protocol_path=PROTOCOL_PATH,
            results_root=results_root,
            executor=executor,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert executor.requests == []


def test_preflight_records_executor_exception_before_propagating(
    tmp_path: Path,
) -> None:
    class _FailingExecutor:
        def execute(self, request: PreflightRunRequest) -> bool:
            raise RuntimeError("provider unavailable")

    results_root = tmp_path / "preflight"

    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_budgeted_context_preflight(
            protocol_path=PROTOCOL_PATH,
            results_root=results_root,
            executor=_FailingExecutor(),
        )

    events = _read_events(results_root / "preflight-events.jsonl")
    assert [event["event"] for event in events] == [
        "run_started",
        "run_failed",
    ]
    assert events[-1]["failure_reason"] == "executor_raised"
    assert events[-1]["error_type"] == "RuntimeError"


def test_preflight_batch_cli_refuses_to_reuse_results_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results_root = tmp_path / "preflight"
    results_root.mkdir()

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(results_root),
        )
    )

    assert exit_code == 2
    assert "Preflight error:" in capsys.readouterr().err


def test_preflight_batch_cli_checks_dirty_repository_before_creating_results(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repository, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=MiniCode Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
        cwd=repository,
        check=True,
    )
    tracked.write_text("after\n", encoding="utf-8")
    results_root = tmp_path / "preflight"

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(results_root),
            "--project-root",
            str(repository),
        )
    )

    assert exit_code == 2
    assert "clean MiniCode repository" in capsys.readouterr().err
    assert not results_root.exists()


def test_preflight_batch_cli_wires_validation_execution_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    class _FakeCommandExecutor:
        def __init__(self, **_: object) -> None:
            calls.append("constructed")

        def validate_environment(self, results_root: Path) -> None:
            assert results_root == tmp_path / "preflight"
            calls.append("validated")

        def execute(self, request: PreflightRunRequest) -> bool:
            calls.append(f"executed:{request.arm}")
            (request.result_directory / "result.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            return True

    def _fake_summary(results_root: Path, protocol_path: Path) -> str:
        assert results_root == tmp_path / "preflight"
        assert protocol_path == PROTOCOL_PATH
        calls.append("summarized")
        return "- Preflight gate: PASS"

    monkeypatch.setattr(
        executor_module,
        "ContextPreflightCommandExecutor",
        _FakeCommandExecutor,
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_context_preflight_results",
        _fake_summary,
    )

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(tmp_path / "preflight"),
        )
    )

    assert exit_code == 0
    assert calls == [
        "constructed",
        "validated",
        "executed:baseline",
        "executed:projection",
        "summarized",
    ]
    assert "Preflight gate: PASS" in capsys.readouterr().out
