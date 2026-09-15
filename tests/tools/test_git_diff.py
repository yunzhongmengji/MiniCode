import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from minicode.tools.base import ToolExecutionError
from minicode.tools.git_diff import GitDiffArguments, GitDiffTool
from minicode.tools.process import (
    AsyncioProcessRunner,
    ProcessOutputLimitError,
    ProcessResult,
)
from minicode.workspace import Workspace


class ScriptedProcessRunner:
    """Return scripted process outcomes while recording each command."""

    def __init__(
        self,
        results: Sequence[ProcessResult | BaseException],
    ) -> None:
        self._results = iter(results)
        self.calls: list[tuple[tuple[str, ...], Path, float]] = []

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        self.calls.append((tuple(command), cwd, timeout_seconds))
        result = next(self._results)

        if isinstance(result, BaseException):
            raise result

        return result


@pytest.mark.asyncio
async def test_git_diff_tool_builds_fixed_commands_and_reports_changes(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    runner = ScriptedProcessRunner(
        (
            ProcessResult(
                exit_code=0,
                stdout=" M src/example.py\n?? src/new.py\n",
                stderr="",
            ),
            ProcessResult(
                exit_code=0,
                stdout="diff --git a/src/example.py b/src/example.py\n",
                stderr="",
            ),
        )
    )
    tool = GitDiffTool(
        Workspace(tmp_path),
        runner=runner,
        timeout_seconds=3.0,
    )

    output = await tool.execute(GitDiffArguments(path="src"))

    assert runner.calls == [
        (
            (
                "git",
                "--literal-pathspecs",
                "--no-pager",
                "status",
                "--short",
                "--untracked-files=all",
                "--",
                "src",
            ),
            tmp_path,
            3.0,
        ),
        (
            (
                "git",
                "--literal-pathspecs",
                "--no-pager",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "HEAD",
                "--",
                "src",
            ),
            tmp_path,
            3.0,
        ),
    ]
    assert " M src/example.py" in output
    assert "?? src/new.py" in output
    assert "diff --git a/src/example.py b/src/example.py" in output
    assert "use read_file to inspect them" in output


@pytest.mark.asyncio
async def test_git_diff_tool_reports_clean_workspace(tmp_path: Path) -> None:
    runner = ScriptedProcessRunner(
        (
            ProcessResult(exit_code=0, stdout="", stderr=""),
            ProcessResult(exit_code=0, stdout="", stderr=""),
        )
    )
    tool = GitDiffTool(Workspace(tmp_path), runner=runner)

    output = await tool.execute(GitDiffArguments())

    assert output == "No Git changes found."


@pytest.mark.asyncio
async def test_git_diff_tool_rejects_workspace_escape(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runner = ScriptedProcessRunner(())
    tool = GitDiffTool(Workspace(workspace_root), runner=runner)

    with pytest.raises(
        ToolExecutionError,
        match="cannot inspect Git changes outside the workspace",
    ):
        await tool.execute(GitDiffArguments(path="../outside"))

    assert runner.calls == []


@pytest.mark.asyncio
async def test_git_diff_tool_translates_process_timeout(tmp_path: Path) -> None:
    runner = ScriptedProcessRunner((TimeoutError("simulated timeout"),))
    tool = GitDiffTool(
        Workspace(tmp_path),
        runner=runner,
        timeout_seconds=0.25,
    )

    with pytest.raises(
        ToolExecutionError,
        match="Git change inspection timed out after 0.25 seconds",
    ) as exc_info:
        await tool.execute(GitDiffArguments())

    assert isinstance(exc_info.value.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_git_diff_tool_translates_process_output_limit(
    tmp_path: Path,
) -> None:
    runner = ScriptedProcessRunner(
        (
            ProcessOutputLimitError(
                stream_name="stderr",
                max_bytes=100,
            ),
        )
    )
    tool = GitDiffTool(
        Workspace(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        ToolExecutionError,
        match="Git stderr exceeds the 100-byte process limit",
    ) as exc_info:
        await tool.execute(GitDiffArguments())

    assert isinstance(
        exc_info.value.__cause__,
        ProcessOutputLimitError,
    )


@pytest.mark.asyncio
async def test_git_diff_tool_rejects_oversized_output(tmp_path: Path) -> None:
    runner = ScriptedProcessRunner(
        (
            ProcessResult(exit_code=0, stdout=" M example.py\n", stderr=""),
            ProcessResult(exit_code=0, stdout="large diff", stderr=""),
        )
    )
    tool = GitDiffTool(
        Workspace(tmp_path),
        runner=runner,
        max_bytes=20,
    )

    with pytest.raises(
        ToolExecutionError,
        match="Git change output exceeds the 20-byte limit",
    ):
        await tool.execute(GitDiffArguments())


@pytest.fixture
def changed_git_repository(tmp_path: Path) -> Path:
    """Create a repository containing tracked and untracked changes."""
    subprocess.run(
        ("git", "init", "-q"),
        cwd=tmp_path,
        check=True,
    )
    tracked_path = tmp_path / "tracked.txt"
    tracked_path.write_text("before\n", encoding="utf-8")
    subprocess.run(
        ("git", "add", "tracked.txt"),
        cwd=tmp_path,
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
            "initial",
        ),
        cwd=tmp_path,
        check=True,
    )
    tracked_path.write_text("after\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_git_diff_tool_runs_against_real_repository(
    changed_git_repository: Path,
) -> None:
    repository = changed_git_repository

    tool = GitDiffTool(
        Workspace(repository),
        runner=AsyncioProcessRunner(),
    )

    output = await tool.execute(GitDiffArguments())

    assert " M tracked.txt" in output
    assert "?? new.txt" in output
    assert "-before" in output
    assert "+after" in output


@pytest.mark.asyncio
async def test_git_diff_tool_treats_git_pathspec_magic_as_a_literal_path(
    changed_git_repository: Path,
) -> None:
    repository = changed_git_repository
    workspace_root = repository / "workspace"
    workspace_root.mkdir()
    tool = GitDiffTool(
        Workspace(workspace_root),
        runner=AsyncioProcessRunner(),
    )

    output = await tool.execute(
        GitDiffArguments(
            path=":(top)**",
        )
    )

    assert output == "No Git changes found."
