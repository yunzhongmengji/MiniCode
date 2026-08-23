"""Dispatch tool calls to registered executable tools."""

from pydantic import ValidationError

from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.base import ToolExecutionError
from minicode.tools.registry import ToolRegistry


class ToolDispatcher:
    """Validate and execute tool calls through a registry."""

    def __init__(
        self,
        registry: ToolRegistry,
    ) -> None:
        self._registry = registry

    async def execute(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:
        """Execute a tool call or return a correlated error result."""
        tool = self._registry.get(tool_call.name)

        if tool is None:
            return ToolResult(
                call_id=tool_call.call_id,
                output=f"unknown tool: {tool_call.name}",
                is_error=True,
            )

        raw_arguments = dict(tool_call.arguments)

        try:
            validated_arguments = tool.spec.arguments_type.model_validate(raw_arguments)
        except ValidationError as error:
            validation_details = error.errors(
                include_url=False,
                include_input=False,
            )
            return ToolResult(
                call_id=tool_call.call_id,
                output=(
                    f"invalid arguments for tool "
                    f"'{tool_call.name}': {validation_details}"
                ),
                is_error=True,
            )

        try:
            output = await tool.execute(validated_arguments)
        except ToolExecutionError as error:
            return ToolResult(
                call_id=tool_call.call_id,
                output=(f"tool '{tool_call.name}' failed: {error}"),
                is_error=True,
            )

        return ToolResult(
            call_id=tool_call.call_id,
            output=output,
            is_error=False,
        )
