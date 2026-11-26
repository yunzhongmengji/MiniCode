"""Provider-neutral model boundary built directly on Pydantic v2 schemas."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from minicode.schemas.messages import HistoryEntry, TokenUsage, ToolCallRecord
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


class ModelAccessDeniedError(ModelError):
    """Raised when access to a model resource is denied."""


class ModelServiceError(ModelError):
    """Raised when a model provider rejects or fails a request."""


class ModelRequest(BaseModel):
    """Provider-neutral input for one model completion turn."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    conversation: tuple[HistoryEntry, ...]
    tool_specs: tuple[ToolSpec, ...] = ()
    instructions: tuple[str, ...] = ()


class ModelResponse(BaseModel):
    """Provider-neutral output from one model completion turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = ""
    tool_calls: tuple[ToolCallRecord, ...] = ()
    usage: TokenUsage | None = None


class Model(Protocol):
    """Asynchronous LLM provider interface."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Produce the next assistant response or proposed tool calls."""
        ...
