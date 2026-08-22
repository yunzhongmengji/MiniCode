"""Tool-execution contract used by MiniCode's query loop."""

from typing import Protocol

from minicode.core.tool_calls import ToolCall, ToolResult


class ToolRuntime(Protocol):
    """Execute tool calls behind a controlled runtime boundary."""

    async def execute(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:
        """Execute one tool call and return its correlated result."""
        ...
