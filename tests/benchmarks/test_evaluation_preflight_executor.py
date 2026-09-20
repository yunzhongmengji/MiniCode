from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import minicode.evaluation_preflight_executor as executor_module
from minicode.evaluation_formal import (
    FormalRunRequest,
    run_budgeted_context_formal_experiment,
)
from minicode.evaluation_preflight import run_budgeted_context_preflight
from minicode.evaluation_preflight_executor import (
    ContextFormalCommandExecutor,
    ContextPreflightCommandExecutor,
    EvaluationCommandResult,
    extract_evaluation_trace,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = (
    PROJECT_ROOT
    / "benchmarks"
    / "context_projection"
    / "real_model_protocol_v4.json"
)


class _FakeCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
    ) -> EvaluationCommandResult:
        self.calls.append((command, cwd))
        module = command[command.index("-m") + 1]

        if module == "minicode.evaluation_run":
            arm = command[command.index("--arm") + 1]
            return EvaluationCommandResult(
                returncode=0,
                stdout=f"completed {arm}\n",
                stderr=(
                    "Run ID: run_fixture\n"
                    "Approve? [y/N]: Trace run_fixture\n"
                    "001 run_started {}\n"
                ),
            )

        assert module == "minicode.evaluation_result"
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            '{"run": {"input_tokens": 100, "output_tokens": 10}}\n',
            encoding="utf-8",
        )
        (output.parent / "workspace.patch").write_text("", encoding="utf-8")
        return EvaluationCommandResult(
            returncode=0,
            stdout="PASS fixture\n",
            stderr="",
        )


def test_command_executor_runs_both_arms_through_existing_cli_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "_assert_clean_repository",
        lambda project_root: None,
    )
    runner = _FakeCommandRunner()
    executor = ContextPreflightCommandExecutor(
        project_root=PROJECT_ROOT,
        temporary_root=tmp_path,
        command_runner=runner,
        python_executable="python-fixture",
    )
    results_root = tmp_path / "preflight"

    result = run_budgeted_context_preflight(
        protocol_path=PROTOCOL_PATH,
        results_root=results_root,
        executor=executor,
    )

    assert result.passed
    assert len(runner.calls) == 4
    assert [
        command[command.index("-m") + 1] for command, _ in runner.calls
    ] == [
        "minicode.evaluation_run",
        "minicode.evaluation_result",
        "minicode.evaluation_run",
        "minicode.evaluation_result",
    ]
    assert [
        command[command.index("--arm") + 1]
        for command, _ in (runner.calls[0], runner.calls[2])
    ] == ["baseline", "projection"]

    for index, arm in ((1, "baseline"), (2, "projection")):
        run_directory = results_root / f"{index:02d}-{arm}"
        assert (run_directory / "answer.txt").read_text(encoding="utf-8") == (
            f"completed {arm}\n"
        )
        assert (run_directory / "stderr.raw.txt").is_file()
        assert (run_directory / "trace.txt").read_text(
            encoding="utf-8"
        ).startswith("Trace run_fixture\n")
        assert (run_directory / "result.json").is_file()
        workspace = Path(
            (run_directory / "workspace.path.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        assert workspace.is_dir()
        assert workspace != PROJECT_ROOT

    result_commands = (runner.calls[1][0], runner.calls[3][0])
    assert [
        command[command.index("--agent-exit-code") + 1]
        for command in result_commands
    ] == ["0", "0"]
    assert all(
        command[command.index("--context-protocol") + 1]
        == str(results_root / "protocol.snapshot.json")
        for command in result_commands
    )


def test_formal_executor_reuses_existing_cli_boundaries_for_all_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "_assert_clean_repository",
        lambda project_root: None,
    )
    runner = _FakeCommandRunner()
    executor = ContextFormalCommandExecutor(
        project_root=PROJECT_ROOT,
        temporary_root=tmp_path,
        command_runner=runner,
        python_executable="python-fixture",
    )

    result = run_budgeted_context_formal_experiment(
        protocol_path=PROTOCOL_PATH,
        results_root=tmp_path / "formal",
        executor=executor,
    )

    assert result.execution_complete
    assert len(runner.calls) == 24
    run_commands = runner.calls[::2]
    assert [command[command.index("--arm") + 1] for command, _ in run_commands] == [
        "baseline",
        "projection",
        "projection",
        "baseline",
        "baseline",
        "projection",
    ] * 2
    assert all((record.request.result_directory / "trace.txt").is_file() for record in result.records)


def test_formal_executor_rejects_wrong_position_before_running_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "_assert_clean_repository",
        lambda project_root: None,
    )
    runner = _FakeCommandRunner()
    executor = ContextFormalCommandExecutor(
        project_root=PROJECT_ROOT,
        temporary_root=tmp_path,
        command_runner=runner,
    )
    result_directory = tmp_path / "formal" / "01-wrong"
    result_directory.mkdir(parents=True)
    request = FormalRunRequest(
        run_index=1,
        protocol_snapshot_path=PROTOCOL_PATH,
        protocol_id="context-editing-budget-real-model-pilot-v4",
        case_id="large_search_context_recall",
        arm="baseline",
        result_directory=result_directory,
    )

    with pytest.raises(ValueError, match="position disagrees"):
        executor.execute(request)

    assert runner.calls == []
    assert not (result_directory / "workspace.path.txt").exists()


def test_trace_extraction_handles_prompt_on_same_line() -> None:
    stderr = (
        "Run ID: run_fixture\n"
        "Approve? [y/N]: Trace run_fixture\n"
        "001 run_started {}\n"
    )

    assert extract_evaluation_trace(stderr) == (
        "Trace run_fixture\n001 run_started {}\n"
    )


@pytest.mark.parametrize(
    "stderr",
    (
        "Run ID: run_fixture\n",
        "Trace run_one\nTrace run_two\n",
    ),
)
def test_trace_extraction_requires_exactly_one_marker(stderr: str) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        extract_evaluation_trace(stderr)


def test_clean_repository_guard_rejects_uncommitted_changes(tmp_path: Path) -> None:
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
    executor_module._assert_clean_repository(repository.resolve())

    tracked.write_text("after\n", encoding="utf-8")

    with pytest.raises(ValueError, match="clean MiniCode repository"):
        executor_module._assert_clean_repository(repository.resolve())


def test_result_directory_guard_rejects_repository_children(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    result_directory = project_root / "generated-results"
    result_directory.mkdir()

    with pytest.raises(ValueError, match="outside the MiniCode repository"):
        executor_module._assert_results_outside_repository(
            result_directory,
            project_root.resolve(),
        )


def test_environment_validation_rejects_repository_result_root_without_creating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    results_root = project_root / "generated-results"
    monkeypatch.setattr(
        executor_module,
        "_assert_clean_repository",
        lambda repository: None,
    )
    executor = ContextPreflightCommandExecutor(project_root=project_root)

    with pytest.raises(ValueError, match="outside the MiniCode repository"):
        executor.validate_environment(results_root)

    assert not results_root.exists()
