"""Model-facing contracts for MiniCode."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from minicode.core.conversation import ConversationItem
from minicode.core.messages import Message
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.spec import ToolSpec


class ModelError(RuntimeError):
    """Base exception for failures at the model boundary."""


class ModelProtocolError(ModelError):
    """Raised when a provider returns an unusable response."""


class ModelAuthenticationError(ModelError):
    """Raised when a model provider rejects authentication."""


class ModelRateLimitError(ModelError):
    """Raised when a model provider rate-limits a request."""


class ModelConnectionError(ModelError):
    """Raised when a model provider cannot be reached."""


class ModelQuotaExceededError(ModelError):
    """Raised when a model provider quota is exhausted."""


class ModelAccessDeniedError(ModelError):
    """Raised when access to a model resource is denied."""


class ModelServiceError(ModelError):
    """Raised when a model provider rejects or fails a request."""


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """A provider-neutral request sent to a model implementation."""

    conversation: Sequence[ConversationItem]
    tool_specs: Sequence[ToolSpec] = ()

    def __post_init__(self) -> None:
        """Validate fields and copy request inputs into immutable snapshots."""
        if not isinstance(self.conversation, Sequence) or isinstance(
            self.conversation,
            (str, bytes),
        ):
            raise TypeError("conversation must be a sequence")

        for item in self.conversation:
            if not isinstance(
                item,
                (Message, ToolCall, ToolResult),
            ):
                raise TypeError(
                    "conversation must contain only ConversationItem instances"
                )

        if not isinstance(self.tool_specs, Sequence) or isinstance(
            self.tool_specs,
            (str, bytes),
        ):
            raise TypeError("tool_specs must be a sequence")

        for tool_spec in self.tool_specs:
            if not isinstance(tool_spec, ToolSpec):
                raise TypeError("tool_specs must contain only ToolSpec instances")

        object.__setattr__(
            self,
            "conversation",
            tuple(self.conversation),
        )
        object.__setattr__(
            self,
            "tool_specs",
            tuple(self.tool_specs),
        )


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
        request: ModelRequest,
    ) -> ModelResponse:
        """Generate the next response from a normalized model request."""
        ...
