"""Static protocol compatibility checks for tool runtimes."""

from minicode.core.tool_runtime import ToolRuntime
from minicode.tools.scripted import ScriptedToolRuntime


def build_scripted_tool_runtime_as_protocol() -> ToolRuntime:
    """Require ScriptedToolRuntime to satisfy ToolRuntime."""
    return ScriptedToolRuntime(
        results=[],
    )
