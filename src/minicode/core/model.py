"""Model-facing contracts for MiniCode."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from minicode.core.conversation import ConversationItem
from minicode.core.tool_calls import ToolCall


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A normalized response returned by any model implementation."""

    content: str
    tool_calls: Sequence[ToolCall] = ()

    def __post_init__(self) -> None:
        """Validate fields and copy tool calls into an immutable snapshot."""
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")

        if not isinstance(self.tool_calls, Sequence) or isinstance(
            self.tool_calls,
            (str, bytes),
        ):
            raise TypeError("tool_calls must be a sequence")

        for tool_call in self.tool_calls:
            if not isinstance(tool_call, ToolCall):
                raise TypeError("tool_calls must contain only ToolCall instances")

        normalized_tool_calls = tuple(self.tool_calls)

        if not self.content.strip() and not normalized_tool_calls:
            raise ValueError("response must contain content or tool calls")

        object.__setattr__(
            self,
            "tool_calls",
            normalized_tool_calls,
        )


class Model(Protocol):
    """The model interface required by MiniCode's query loop."""

    async def complete(
        self,
        messages: Sequence[ConversationItem],
    ) -> ModelResponse:
        """Generate the next response from the conversation history."""
        ...
