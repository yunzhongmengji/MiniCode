"""Dispatch tool calls to registered executable tools."""

from pydantic import ValidationError

from minicode.core.tool_approval import ToolApprover
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.core.tool_policy import (
    PolicyDecision,
    PolicyOutcome,
    ToolPolicy,
)
from minicode.tools.base import ToolExecutionError
from minicode.tools.registry import ToolRegistry


class ToolDispatcher:
    """Validate and execute tool calls through a registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        policy: ToolPolicy,
        approver: ToolApprover | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._approver = approver

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

        decision = self._policy.evaluate(tool_call)

        if not isinstance(
            decision,
            PolicyDecision,
        ):
            raise TypeError("policy must return a PolicyDecision")

        if decision.outcome is PolicyOutcome.DENY:
            return ToolResult(
                call_id=tool_call.call_id,
                output=(f"tool '{tool_call.name}' denied by policy"),
                is_error=True,
            )

        if decision.outcome is PolicyOutcome.ASK:
            if self._approver is None:
                return ToolResult(
                    call_id=tool_call.call_id,
                    output=(f"tool '{tool_call.name}' requires approval"),
                    is_error=True,
                )

            approved = await self._approver.request_approval(
                tool_call,
                reason=decision.reason,
            )

            if not isinstance(approved, bool):
                raise TypeError("approver must return a boolean")

            if not approved:
                return ToolResult(
                    call_id=tool_call.call_id,
                    output=(f"tool '{tool_call.name}' approval denied"),
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
