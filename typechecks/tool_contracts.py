"""Static compatibility checks for MiniCode tool contracts."""

from minicode.core.tool_runtime import ToolRuntime
from minicode.tools.base import Tool
from minicode.tools.dispatcher import ToolDispatcher
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.tools.spec import ToolSpec


def build_scripted_tool_runtime_as_protocol() -> ToolRuntime:
    """Require ScriptedToolRuntime to satisfy ToolRuntime."""
    return ScriptedToolRuntime(
        results=[],
    )


class ExampleArguments(ToolArguments):
    """Arguments used by the static example tool."""

    text: str


class ExampleTool:
    """Minimal implementation used only for static checking."""

    @property
    def spec(self) -> ToolSpec:
        """Return metadata for this example tool."""
        return ToolSpec(
            name="example",
            description="Return validated example arguments.",
            arguments_type=ExampleArguments,
        )

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Return the validated arguments as JSON."""
        return arguments.model_dump_json()


def build_example_tool_as_protocol() -> Tool:
    """Require ExampleTool to satisfy the Tool protocol."""
    return ExampleTool()


def build_tool_dispatcher_as_runtime_protocol() -> ToolRuntime:
    """Require ToolDispatcher to satisfy the ToolRuntime protocol."""
    return ToolDispatcher(
        registry=ToolRegistry(),
    )
