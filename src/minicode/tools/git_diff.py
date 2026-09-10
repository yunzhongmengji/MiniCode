"""Tool for inspecting Git changes inside a workspace."""

from collections.abc import Sequence

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.process import ProcessResult, ProcessRunner
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import Workspace, WorkspacePathError

_DEFAULT_MAX_BYTES = 100_000
_DEFAULT_TIMEOUT_SECONDS = 10.0


class GitDiffArguments(ToolArguments):
    """Validated arguments accepted by the Git-change inspection tool."""

    path: str = Field(
        default=".",
        description=("Workspace file or directory whose Git changes should be shown."),
    )

    @field_validator("path")
    @classmethod
    def validate_path_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject paths containing only whitespace."""
        if not value.strip():
            raise ValueError("path must not be blank")

        return value


_GIT_DIFF_SPEC = ToolSpec(
    name="git_diff",
    description=(
        "Show bounded Git status and tracked-file changes under a workspace path. "
        "Untracked files are listed but their contents are not included."
    ),
    arguments_type=GitDiffArguments,
)


class GitDiffTool:
    """Inspect repository changes without modifying the worktree or index."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        runner: ProcessRunner,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds,
            (int, float),
        ):
            raise TypeError("timeout_seconds must be numeric")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        self._workspace = workspace
        self._runner = runner
        self._timeout_seconds = float(timeout_seconds)
        self._max_bytes = max_bytes

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _GIT_DIFF_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Return Git status and the tracked-file diff against HEAD."""
        if not isinstance(arguments, GitDiffArguments):
            raise TypeError("arguments must be GitDiffArguments")

        try:
            selected_path = self._workspace.resolve_path(arguments.path)
        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot inspect Git changes outside the workspace: {arguments.path}"
            ) from error

        relative_path = selected_path.relative_to(self._workspace.root).as_posix()
        status_command = (
            "git",
            "--no-pager",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            relative_path,
        )
        diff_command = (
            "git",
            "--no-pager",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "HEAD",
            "--",
            relative_path,
        )

        status_result = await self._run_git(status_command)
        self._require_success(status_result)

        diff_result = await self._run_git(diff_command)
        self._require_success(diff_result)

        status = status_result.stdout.rstrip()
        diff = diff_result.stdout.rstrip()

        if not status and not diff:
            return "No Git changes found."

        sections = [
            "Git status:\n" + (status or "No changed paths."),
            "Tracked-file diff against HEAD:\n" + (diff or "No tracked-file changes."),
        ]

        if any(line.startswith("?? ") for line in status.splitlines()):
            sections.append(
                "Untracked file contents are not included; use read_file to inspect them."
            )

        output = "\n\n".join(sections)

        if len(output.encode("utf-8")) > self._max_bytes:
            raise ToolExecutionError(
                "Git change output exceeds "
                f"the {self._max_bytes}-byte limit; narrow the path"
            )

        return output

    async def _run_git(
        self,
        command: Sequence[str],
    ) -> ProcessResult:
        try:
            return await self._runner.run(
                command,
                cwd=self._workspace.root,
                timeout_seconds=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise ToolExecutionError(
                f"Git change inspection timed out after {self._timeout_seconds} seconds"
            ) from error

    @staticmethod
    def _require_success(result: ProcessResult) -> None:
        if result.exit_code == 0:
            return

        detail = "\n".join(
            part for part in (result.stdout.strip(), result.stderr.strip()) if part
        )
        suffix = f":\n{detail}" if detail else ""
        raise ToolExecutionError(
            f"Git change inspection failed with exit code {result.exit_code}{suffix}"
        )
