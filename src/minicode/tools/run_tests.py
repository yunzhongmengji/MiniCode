"""Tool for running pytest inside a workspace."""

import sys

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.process import ProcessOutputLimitError, ProcessRunner
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import (
    Workspace,
    WorkspacePathError,
)


class RunTestsArguments(ToolArguments):
    """Validated arguments accepted by the pytest tool."""

    path: str = Field(
        default="tests",
        description=("Test file or directory to run, relative to the workspace root."),
    )

    @field_validator("path")
    @classmethod
    def validate_path(
        cls,
        value: str,
    ) -> str:
        """Reject blank paths and pytest options."""
        if not value.strip():
            raise ValueError("path must not be blank")

        if value.startswith("-"):
            raise ValueError("path must not start with '-'")

        return value


_DEFAULT_TIMEOUT_SECONDS = 120.0


_RUN_TESTS_SPEC = ToolSpec(
    name="run_tests",
    description=("Run pytest for one workspace test file or directory."),
    arguments_type=RunTestsArguments,
)


class RunTestsTool:
    """Run selected pytest tests inside a workspace."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        runner: ProcessRunner,
        timeout_seconds: float = (_DEFAULT_TIMEOUT_SECONDS),
    ) -> None:
        if isinstance(
            timeout_seconds,
            bool,
        ) or not isinstance(
            timeout_seconds,
            (int, float),
        ):
            raise TypeError("timeout_seconds must be numeric")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        self._workspace = workspace
        self._runner = runner
        self._timeout_seconds = float(timeout_seconds)

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _RUN_TESTS_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Run pytest for one selected path."""
        if not isinstance(
            arguments,
            RunTestsArguments,
        ):
            raise TypeError("arguments must be RunTestsArguments")

        try:
            selected_path = self._workspace.resolve_path(arguments.path)

            if not selected_path.exists():
                raise FileNotFoundError(f"test path does not exist: {arguments.path}")

        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot run tests outside the workspace: {arguments.path}"
            ) from error
        except FileNotFoundError as error:
            raise ToolExecutionError(
                f"test path not found: {arguments.path}"
            ) from error

        relative_path = selected_path.relative_to(self._workspace.root).as_posix()

        command = (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--",
            relative_path,
        )

        try:
            result = await self._runner.run(
                command,
                cwd=self._workspace.root,
                timeout_seconds=(self._timeout_seconds),
            )
        except TimeoutError as error:
            raise ToolExecutionError(
                f"pytest timed out after {self._timeout_seconds} seconds"
            ) from error
        except ProcessOutputLimitError as error:
            raise ToolExecutionError(
                f"pytest {error.stream_name} exceeds the {error.max_bytes}-byte limit"
            ) from error

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        output = "\n".join(
            part
            for part in (
                stdout,
                stderr,
            )
            if part
        )

        if result.exit_code != 0:
            raise ToolExecutionError(
                f"pytest failed with exit code {result.exit_code}:\n{output}"
            )

        return output
