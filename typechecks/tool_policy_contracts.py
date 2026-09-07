"""Static protocol checks for tool-policy implementations."""

from minicode.core.tool_calls import ToolCall
from minicode.core.tool_policy import (
    PolicyDecision,
    PolicyOutcome,
    ToolPolicy,
)


class ReadOnlyPolicy:
    """Example structurally compatible policy."""

    def evaluate(
        self,
        tool_call: ToolCall,
    ) -> PolicyDecision:
        return PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            reason=(f"read-only tool is allowed: {tool_call.name}"),
        )


def build_policy() -> ToolPolicy:
    return ReadOnlyPolicy()
