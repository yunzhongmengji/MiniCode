from __future__ import annotations

import json
from pathlib import Path

import pytest

import minicode.evaluation_preflight_executor as executor_module
import minicode.evaluation_summary as summary_module
from minicode.evaluation_formal import (
    FormalRunRequest,
    main,
    run_budgeted_context_formal_experiment,
)

PROTOCOL_PATH = Path("benchmarks/context_projection/real_model_protocol_v4.json")


class _RecordingExecutor:
    def __init__(
        self,
        *,
        outcomes: tuple[bool, ...],
        input_tokens: int = 100,
        output_tokens: int = 10,
        missing_result_at: int | None = None,
    ) -> None:
        self._outcomes = iter(outcomes)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._missing_result_at = missing_result_at
        self.requests: list[FormalRunRequest] = []

    def execute(self, request: FormalRunRequest) -> bool:
        self.requests.append(request)

        if request.run_index != self._missing_result_at:
            (request.result_directory / "result.json").write_text(
                json.dumps(
                    {
                        "run": {
                            "input_tokens": self._input_tokens,
                            "output_tokens": self._output_tokens,
                        }
                    }
                ),
                encoding="utf-8",
            )

        return next(self._outcomes)


def _read_events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _write_protocol_with_input_budget(path: Path, maximum: int) -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["formal_budget"]["maximum_input_tokens"] = maximum
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_formal_orchestrator_freezes_all_twelve_samples_in_order(
    tmp_path: Path,
) -> None:
    executor = _RecordingExecutor(outcomes=(True,) * 12)
    results_root = tmp_path / "formal"

    result = run_budgeted_context_formal_experiment(
        protocol_path=PROTOCOL_PATH,
        results_root=results_root,
        executor=executor,
    )

    assert result.execution_complete
    assert result.budget_within_limits
    assert result.stop_reason is None
    assert result.input_tokens == 1200
    assert result.output_tokens == 120
    assert [
        (request.case_id, request.arm) for request in executor.requests
    ] == [
        ("large_search_context_repair", "baseline"),
        ("large_search_context_repair", "projection"),
        ("large_search_context_repair", "projection"),
        ("large_search_context_repair", "baseline"),
        ("large_search_context_repair", "baseline"),
        ("large_search_context_repair", "projection"),
        ("large_search_context_recall", "baseline"),
        ("large_search_context_recall", "projection"),
        ("large_search_context_recall", "projection"),
        ("large_search_context_recall", "baseline"),
        ("large_search_context_recall", "baseline"),
        ("large_search_context_recall", "projection"),
    ]
    assert (results_root / "protocol.snapshot.json").read_bytes() == (
        PROTOCOL_PATH.read_bytes()
    )
    plan = json.loads((results_root / "formal-plan.json").read_text())
    assert plan["budget"] == {
        "maximum_input_tokens": 270000,
        "maximum_output_tokens": 30000,
        "maximum_runs": 12,
    }
    assert len(plan["runs"]) == 12
    assert len(_read_events(results_root / "formal-events.jsonl")) == 24


def test_formal_orchestrator_keeps_failed_task_as_a_sample(tmp_path: Path) -> None:
    executor = _RecordingExecutor(outcomes=(False,) + (True,) * 11)

    result = run_budgeted_context_formal_experiment(
        protocol_path=PROTOCOL_PATH,
        results_root=tmp_path / "formal",
        executor=executor,
    )

    assert result.execution_complete
    assert len(executor.requests) == 12
    assert not result.records[0].task_passed
    assert all(record.task_passed for record in result.records[1:])


def test_formal_orchestrator_stops_when_result_record_is_missing(
    tmp_path: Path,
) -> None:
    executor = _RecordingExecutor(
        outcomes=(True,) * 12,
        missing_result_at=2,
    )

    result = run_budgeted_context_formal_experiment(
        protocol_path=PROTOCOL_PATH,
        results_root=tmp_path / "formal",
        executor=executor,
    )

    assert not result.execution_complete
    assert result.stop_reason == "result_json_missing"
    assert len(result.records) == 1
    assert len(executor.requests) == 2


def test_formal_orchestrator_stops_after_crossing_provider_budget(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    _write_protocol_with_input_budget(protocol_path, 150)
    executor = _RecordingExecutor(outcomes=(True,) * 12)

    result = run_budgeted_context_formal_experiment(
        protocol_path=protocol_path,
        results_root=tmp_path / "formal",
        executor=executor,
    )

    assert not result.execution_complete
    assert not result.budget_within_limits
    assert result.stop_reason == "formal_budget_exceeded"
    assert len(result.records) == 2
    assert len(executor.requests) == 2
    assert _read_events(result.results_root / "formal-events.jsonl")[-1][
        "budget_exceeded"
    ]


def test_formal_orchestrator_never_reuses_results_root(tmp_path: Path) -> None:
    results_root = tmp_path / "formal"
    results_root.mkdir()
    sentinel = results_root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    executor = _RecordingExecutor(outcomes=(True,) * 12)

    try:
        run_budgeted_context_formal_experiment(
            protocol_path=PROTOCOL_PATH,
            results_root=results_root,
            executor=executor,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing formal results root was reused")

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert executor.requests == []


def test_formal_batch_cli_wires_validation_execution_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    class _FakeCommandExecutor:
        def __init__(self, **_: object) -> None:
            calls.append("constructed")

        def validate_environment(self, results_root: Path) -> None:
            assert results_root == tmp_path / "formal"
            calls.append("validated")

        def execute(self, request: FormalRunRequest) -> bool:
            calls.append(f"executed:{request.run_index}:{request.arm}")
            (request.result_directory / "result.json").write_text(
                json.dumps(
                    {
                        "run": {"input_tokens": 100, "output_tokens": 10},
                        "verdict": {"passed": True},
                    }
                ),
                encoding="utf-8",
            )
            return True

    def _fake_summary(results_root: Path, protocol_path: Path) -> str:
        assert results_root == tmp_path / "formal"
        assert protocol_path == PROTOCOL_PATH
        calls.append("summarized")
        return "- Advancement gate: PASS"

    monkeypatch.setattr(
        executor_module,
        "ContextFormalCommandExecutor",
        _FakeCommandExecutor,
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_context_experiment_results",
        _fake_summary,
    )

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(tmp_path / "formal"),
        )
    )

    assert exit_code == 0
    assert calls[:2] == ["constructed", "validated"]
    assert calls[2:-1] == [
        f"executed:{index}:{arm}"
        for index, arm in enumerate(
            (
                "baseline",
                "projection",
                "projection",
                "baseline",
                "baseline",
                "projection",
            )
            * 2,
            start=1,
        )
    ]
    assert calls[-1] == "summarized"
    assert "Advancement gate: PASS" in capsys.readouterr().out


def test_formal_batch_cli_stops_without_result_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _MissingResultExecutor:
        def __init__(self, **_: object) -> None:
            pass

        def validate_environment(self, results_root: Path) -> None:
            pass

        def execute(self, request: FormalRunRequest) -> bool:
            return True

    monkeypatch.setattr(
        executor_module,
        "ContextFormalCommandExecutor",
        _MissingResultExecutor,
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_context_experiment_results",
        lambda *_: (_ for _ in ()).throw(AssertionError("summary called")),
    )

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(tmp_path / "formal"),
        )
    )

    assert exit_code == 1
    assert "stopped after 0/12 recorded samples" in capsys.readouterr().err


def test_formal_batch_cli_returns_one_when_advancement_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RecordedResultExecutor:
        def __init__(self, **_: object) -> None:
            pass

        def validate_environment(self, results_root: Path) -> None:
            pass

        def execute(self, request: FormalRunRequest) -> bool:
            (request.result_directory / "result.json").write_text(
                json.dumps(
                    {
                        "run": {"input_tokens": 100, "output_tokens": 10},
                        "verdict": {"passed": True},
                    }
                ),
                encoding="utf-8",
            )
            return True

    monkeypatch.setattr(
        executor_module,
        "ContextFormalCommandExecutor",
        _RecordedResultExecutor,
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_context_experiment_results",
        lambda *_: "- Advancement gate: FAIL",
    )

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(tmp_path / "formal"),
        )
    )

    assert exit_code == 1


def test_formal_batch_cli_validates_before_creating_results_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _RejectedEnvironmentExecutor:
        def __init__(self, **_: object) -> None:
            pass

        def validate_environment(self, results_root: Path) -> None:
            raise ValueError("unsafe fixture")

    monkeypatch.setattr(
        executor_module,
        "ContextFormalCommandExecutor",
        _RejectedEnvironmentExecutor,
    )
    results_root = tmp_path / "formal"

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--results-root",
            str(results_root),
        )
    )

    assert exit_code == 2
    assert "unsafe fixture" in capsys.readouterr().err
    assert not results_root.exists()
