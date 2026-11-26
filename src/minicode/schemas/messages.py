"""Unified Pydantic v2 schemas for messages, tool calls, and token usage."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    """Role of a conversational message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class TokenUsage(BaseModel):
    """Token accounting recorded for one model invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed by the invocation."""
        return self.input_tokens + self.output_tokens


class MessageRecord(BaseModel):
    """Serializable conversational message stored in checkpoints and sent to models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["message"] = "message"
    role: MessageRole
    content: str


class ToolCallRecord(BaseModel):
    """Serializable model-proposed tool invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["tool_call"] = "tool_call"
    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultRecord(BaseModel):
    """Serializable tool execution output correlated to a ToolCallRecord."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["tool_result"] = "tool_result"
    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    output: str
    is_error: bool = False


HistoryEntry = Annotated[
    MessageRecord | ToolCallRecord | ToolResultRecord,
    Field(discriminator="kind"),
]
