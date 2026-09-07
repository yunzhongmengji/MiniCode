"""Approval boundary for policy-gated tool execution."""

from typing import Protocol

from minicode.core.tool_calls import ToolCall


class ToolApprover(Protocol):
    """Request approval for one exact tool call."""

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        """Return whether this exact tool call was approved."""
        ...
