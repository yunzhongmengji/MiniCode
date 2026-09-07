import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.tools.base import ToolExecutionError
from minicode.tools.dispatcher import ToolDispatcher
from minicode.tools.process import (
    AsyncioProcessRunner,
    ProcessResult,
)
from minicode.tools.registry import ToolRegistry
from minicode.tools.run_tests import (
    RunTestsArguments,
    RunTestsTool,
)
from minicode.tools.spec import ToolSpec
from minicode.workspace import Workspace


class RecordingProcessRunner:
    """Record commands without starting a real process."""

    def __init__(
        self,
        *,
        result: ProcessResult,
    ) -> None:
        self._result = result
        self.calls: list[
            tuple[
                tuple[str, ...],
                Path,
                float,
            ]
        ] = []

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        self.calls.append(
            (
                tuple(command),
                cwd,
                timeout_seconds,
            )
        )
        return self._result


class TimingOutProcessRunner:
    """Simulate a process timeout."""

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        del command, cwd, timeout_seconds
        raise TimeoutError("simulated process timeout")


class FixedRunTestsApprover:
    """Return one configured approval answer."""

    def __init__(
        self,
        *,
        approved: bool,
    ) -> None:
        self._approved = approved
        self.requests: list[tuple[ToolCall, str]] = []

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        self.requests.append(
            (
                tool_call,
                reason,
            )
        )
        return self._approved


def test_run_tests_arguments_default_to_test_directory() -> None:
    arguments = RunTestsArguments()

    assert arguments.path == "tests"


def test_run_tests_arguments_preserve_selected_path() -> None:
    arguments = RunTestsArguments(
        path="tests/tools",
    )

    assert arguments.path == "tests/tools"


def test_run_tests_tool_exposes_spec(
    tmp_path: Path,
) -> None:
    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="",
            stderr="",
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=runner,
    )

    assert tool.spec == ToolSpec(
        name="run_tests",
        description=("Run pytest for one workspace test file or directory."),
        arguments_type=RunTestsArguments,
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        "\t",
    ],
)
def test_run_tests_arguments_reject_blank_path(
    path: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="path must not be blank",
    ):
        RunTestsArguments(
            path=path,
        )


@pytest.mark.parametrize(
    "path",
    [
        "-p",
        "--rootdir=/tmp",
        "-",
    ],
)
def test_run_tests_arguments_reject_pytest_options(
    path: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=("path must not start with '-'"),
    ):
        RunTestsArguments(
            path=path,
        )


@pytest.mark.asyncio
async def test_run_tests_tool_builds_fixed_pytest_command(
    tmp_path: Path,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="1 passed in 0.10s\n",
            stderr="",
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=runner,
        timeout_seconds=30.0,
    )
    arguments = RunTestsArguments(
        path="tests",
    )

    output = await tool.execute(arguments)

    assert output == "1 passed in 0.10s"
    assert runner.calls == [
        (
            (
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
            ),
            tmp_path.resolve(),
            30.0,
        )
    ]


@pytest.mark.asyncio
async def test_run_tests_tool_rejects_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_tests = tmp_path / "outside-tests"
    outside_tests.mkdir()

    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="should not run",
            stderr="",
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=workspace_root,
        ),
        runner=runner,
    )
    arguments = RunTestsArguments(
        path="../outside-tests",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot run tests outside the workspace: ../outside-tests"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )
    assert runner.calls == []


@pytest.mark.asyncio
async def test_run_tests_tool_rejects_missing_path(
    tmp_path: Path,
) -> None:
    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="should not run",
            stderr="",
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=runner,
    )
    arguments = RunTestsArguments(
        path="missing-tests",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("test path not found: missing-tests"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        FileNotFoundError,
    )
    assert runner.calls == []


@pytest.mark.asyncio
async def test_run_tests_tool_reports_failing_tests(
    tmp_path: Path,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=1,
            stdout=("FAILED tests/test_example.py\n"),
            stderr="",
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=runner,
    )
    arguments = RunTestsArguments(
        path="tests",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("pytest failed with exit code 1"),
    ) as exc_info:
        await tool.execute(arguments)

    assert str(exc_info.value) == (
        "pytest failed with exit code 1:\nFAILED tests/test_example.py"
    )
    assert len(runner.calls) == 1


@pytest.mark.asyncio
async def test_run_tests_tool_includes_stderr_on_failure(
    tmp_path: Path,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=2,
            stdout="",
            stderr=("ERROR collecting tests/test_example.py\n"),
        ),
    )
    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=runner,
    )
    arguments = RunTestsArguments(
        path="tests",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("ERROR collecting tests/test_example.py"),
    ) as exc_info:
        await tool.execute(arguments)

    assert str(exc_info.value) == (
        "pytest failed with exit code 2:\nERROR collecting tests/test_example.py"
    )


@pytest.mark.asyncio
async def test_run_tests_tool_translates_process_timeout(
    tmp_path: Path,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=TimingOutProcessRunner(),
        timeout_seconds=0.25,
    )
    arguments = RunTestsArguments(
        path="tests",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("pytest timed out after 0.25 seconds"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        TimeoutError,
    )


@pytest.mark.parametrize(
    "timeout_seconds",
    [
        None,
        "1",
        True,
    ],
)
def test_run_tests_tool_rejects_non_numeric_timeout(
    tmp_path: Path,
    timeout_seconds: object,
) -> None:
    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="",
            stderr="",
        ),
    )

    with pytest.raises(
        TypeError,
        match="timeout_seconds must be numeric",
    ):
        RunTestsTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            runner=runner,
            timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "timeout_seconds",
    [
        0,
        -1,
        -0.5,
    ],
)
def test_run_tests_tool_rejects_non_positive_timeout(
    tmp_path: Path,
    timeout_seconds: float,
) -> None:
    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="",
            stderr="",
        ),
    )

    with pytest.raises(
        ValueError,
        match=("timeout_seconds must be greater than zero"),
    ):
        RunTestsTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            runner=runner,
            timeout_seconds=timeout_seconds,
        )


@pytest.mark.asyncio
async def test_run_tests_tool_runs_real_pytest_process(
    tmp_path: Path,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    test_file = tests_directory / "test_sample.py"
    test_file.write_text(
        ("def test_sample() -> None:\n    assert 2 + 2 == 4\n"),
        encoding="utf-8",
    )

    tool = RunTestsTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        runner=AsyncioProcessRunner(),
        timeout_seconds=10.0,
    )
    arguments = RunTestsArguments(
        path="tests",
    )

    output = await tool.execute(arguments)

    assert "1 passed" in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "approved",
        "expected_output",
        "expected_error",
        "expected_runner_calls",
    ),
    [
        (
            True,
            "1 passed in 0.10s",
            False,
            1,
        ),
        (
            False,
            "tool 'run_tests' approval denied",
            True,
            0,
        ),
    ],
)
async def test_run_tests_tool_respects_approval(
    tmp_path: Path,
    approved: bool,
    expected_output: str,
    expected_error: bool,
    expected_runner_calls: int,
) -> None:
    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    runner = RecordingProcessRunner(
        result=ProcessResult(
            exit_code=0,
            stdout="1 passed in 0.10s\n",
            stderr="",
        ),
    )

    registry = ToolRegistry()
    registry.register(
        RunTestsTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            runner=runner,
        )
    )

    policy_reason = "running tests requires approval"
    policy = ConfiguredToolPolicy(
        decisions={
            "run_tests": PolicyDecision(
                outcome=PolicyOutcome.ASK,
                reason=policy_reason,
            ),
        },
    )
    approver = FixedRunTestsApprover(
        approved=approved,
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        approver=approver,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="run_tests",
        arguments={
            "path": "tests",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output=expected_output,
        is_error=expected_error,
    )
    assert len(runner.calls) == (expected_runner_calls)
    assert approver.requests == [
        (
            tool_call,
            policy_reason,
        )
    ]
