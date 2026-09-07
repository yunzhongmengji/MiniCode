"""Model-facing contracts for MiniCode."""

from collections.abc import AsyncIterator, Sequence
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
class ModelTextDelta:
    """A newly generated fragment of model text."""

    text: str

    def __post_init__(self) -> None:
        """Validate the streamed text fragment."""
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

        if self.text == "":
            raise ValueError("text must not be empty")


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Provider-neutral token usage for one model response."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        """Validate token counts."""
        token_counts = (
            (
                "input_tokens",
                self.input_tokens,
            ),
            (
                "output_tokens",
                self.output_tokens,
            ),
        )

        for field_name, value in token_counts:
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")

            if value < 0:
                raise ValueError(f"{field_name} must not be negative")

    @property
    def total_tokens(self) -> int:
        """Return the total number of consumed tokens."""
        return self.input_tokens + self.output_tokens


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
    usage: ModelUsage | None = None

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

        if self.usage is not None and not isinstance(
            self.usage,
            ModelUsage,
        ):
            raise TypeError("usage must be a ModelUsage or None")

        object.__setattr__(
            self,
            "tool_calls",
            normalized_tool_calls,
        )


@dataclass(frozen=True, slots=True)
class ModelResponseDone:
    """The completed response produced by a model stream."""

    response: ModelResponse

    def __post_init__(self) -> None:
        """Validate the completed stream response."""
        if not isinstance(self.response, ModelResponse):
            raise TypeError("response must be a ModelResponse")


type ModelStreamEvent = ModelTextDelta | ModelResponseDone


class Model(Protocol):
    """The model interface required by MiniCode's query loop."""

    async def complete(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """Generate the next response from a normalized model request."""
        ...


class StreamingModel(Protocol):
    """A model capable of producing incremental events."""

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Stream incremental events for one model request."""
        ...
