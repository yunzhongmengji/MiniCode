"""Coding tools routed into DockerSandbox for isolated mutations and tests."""

from __future__ import annotations

from pydantic import Field

from minicode.runtime.workspace import Workspace
from minicode.sandbox.base import SandboxError
from minicode.sandbox.docker import DockerSandbox
from minicode.tools.base import ToolExecutionError
from minicode.tools.list_files import ListFilesTool
from minicode.tools.read_file import ReadFileTool
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.search_text import SearchTextTool
from minicode.tools.spec import ToolSpec


class SandboxCreateFileArgs(ToolArguments):
    path: str = Field(min_length=1)
    content: str


class SandboxEditFileArgs(ToolArguments):
    path: str = Field(min_length=1)
    old_text: str = Field(min_length=1)
    new_text: str


class SandboxRunTestsArgs(ToolArguments):
    target: str | None = None


class SandboxRunShellArgs(ToolArguments):
    command: list[str] = Field(min_length=1)


class SandboxCreateFileTool:
    """Create a new file strictly inside the DockerSandbox container."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox
        self._spec = ToolSpec(
            name="create_file",
            description="Create a new file inside the isolated Docker sandbox.",
            arguments_type=SandboxCreateFileArgs,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        if not isinstance(arguments, SandboxCreateFileArgs):
            raise TypeError("arguments must be SandboxCreateFileArgs")
        try:
            return await self._sandbox.write_file(
                arguments.path,
                arguments.content,
                overwrite=False,
            )
        except SandboxError as error:
            raise ToolExecutionError(str(error)) from error


class SandboxEditFileTool:
    """Edit an existing file strictly inside the DockerSandbox container."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox
        self._spec = ToolSpec(
            name="edit_file",
            description="Edit an existing file inside the isolated Docker sandbox.",
            arguments_type=SandboxEditFileArgs,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        if not isinstance(arguments, SandboxEditFileArgs):
            raise TypeError("arguments must be SandboxEditFileArgs")
        try:
            return await self._sandbox.edit_file(
                arguments.path,
                arguments.old_text,
                arguments.new_text,
            )
        except SandboxError as error:
            raise ToolExecutionError(str(error)) from error


class SandboxRunTestsTool:
    """Run pytest strictly inside the DockerSandbox container."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox
        self._spec = ToolSpec(
            name="run_tests",
            description="Run pytest inside the isolated Docker sandbox.",
            arguments_type=SandboxRunTestsArgs,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        if not isinstance(arguments, SandboxRunTestsArgs):
            raise TypeError("arguments must be SandboxRunTestsArgs")
        try:
            res = await self._sandbox.run_tests(arguments.target)
        except SandboxError as error:
            raise ToolExecutionError(str(error)) from error
        combined = f"exit_code={res.exit_code}\n{res.stdout}\n{res.stderr}".strip()
        if res.exit_code != 0:
            raise ToolExecutionError(combined)
        return combined


class SandboxRunShellTool:
    """Execute a command argument vector strictly inside the DockerSandbox."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox
        self._spec = ToolSpec(
            name="run_shell",
            description="Run a command inside the isolated Docker sandbox (no network).",
            arguments_type=SandboxRunShellArgs,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        if not isinstance(arguments, SandboxRunShellArgs):
            raise TypeError("arguments must be SandboxRunShellArgs")
        try:
            res = await self._sandbox.exec(arguments.command)
        except SandboxError as error:
            raise ToolExecutionError(str(error)) from error
        combined = f"exit_code={res.exit_code}\n{res.stdout}\n{res.stderr}".strip()
        if res.exit_code != 0:
            raise ToolExecutionError(combined)
        return combined


def build_sandbox_tool_registry(
    *,
    sandbox: DockerSandbox,
    workspace: Workspace,
) -> ToolRegistry:
    """Build a tool registry routing all mutations and test runs into DockerSandbox."""
    registry = ToolRegistry()
    registry.register(ListFilesTool(workspace=workspace))
    registry.register(ReadFileTool(workspace=workspace))
    registry.register(SearchTextTool(workspace=workspace))
    registry.register(SandboxCreateFileTool(sandbox))
    registry.register(SandboxEditFileTool(sandbox))
    registry.register(SandboxRunTestsTool(sandbox))
    registry.register(SandboxRunShellTool(sandbox))
    return registry
