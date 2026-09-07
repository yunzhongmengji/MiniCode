"""Provider-neutral policy decisions for tool execution."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from minicode.core.tool_calls import ToolCall


class PolicyOutcome(StrEnum):
    """Possible outcomes of evaluating one tool action."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Result of evaluating one proposed tool action."""

    outcome: PolicyOutcome
    reason: str

    def __post_init__(self) -> None:
        """Validate one policy decision."""

        if not isinstance(
            self.outcome,
            PolicyOutcome,
        ):
            raise TypeError("outcome must be a PolicyOutcome")

        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")

        if not self.reason.strip():
            raise ValueError("reason must not be blank")


class ToolPolicy(Protocol):
    """Decide whether a proposed tool call may proceed."""

    def evaluate(
        self,
        tool_call: ToolCall,
    ) -> PolicyDecision:
        """Evaluate one proposed tool call without executing it."""
        ...


_DEFAULT_DENY_DECISION = PolicyDecision(
    outcome=PolicyOutcome.DENY,
    reason="tool is not configured by policy",
)


class ConfiguredToolPolicy:
    """Evaluate tool calls using configured name-based decisions."""

    def __init__(
        self,
        *,
        decisions: Mapping[str, PolicyDecision],
    ) -> None:
        if not isinstance(decisions, Mapping):
            raise TypeError("decisions must be a mapping")

        for tool_name, decision in decisions.items():
            if not isinstance(tool_name, str):
                raise TypeError("policy tool names must be strings")

            if not tool_name.strip():
                raise ValueError("policy tool names must not be blank")

            if not isinstance(
                decision,
                PolicyDecision,
            ):
                raise TypeError("policy rules must be PolicyDecision instances")

        self._decisions = dict(decisions)

    def evaluate(
        self,
        tool_call: ToolCall,
    ) -> PolicyDecision:
        """Return the configured decision or deny by default."""
        return self._decisions.get(
            tool_call.name,
            _DEFAULT_DENY_DECISION,
        )
