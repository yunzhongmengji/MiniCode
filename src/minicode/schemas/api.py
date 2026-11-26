"""Pydantic v2 request and response schemas for the FastAPI + SSE service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from minicode.schemas.checkpoints import (
    ApprovalDecision,
    PendingApproval,
    SessionStatus,
)
from minicode.schemas.events import EventType
from minicode.schemas.messages import TokenUsage


class CreateTaskRequest(BaseModel):
    """Payload for POST /tasks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    max_turns: int = Field(default=8, ge=1, le=50)
    max_tool_calls: int = Field(default=16, ge=1, le=100)
    max_context_tokens: int | None = Field(default=None, ge=128)


class ApproveTaskRequest(BaseModel):
    """Payload for POST /tasks/{id}/approve."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ApprovalDecision
    reason: str = ""


class TaskResponse(BaseModel):
    """Status summary returned by task lifecycle endpoints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1)
    status: SessionStatus
    step: int = Field(ge=0)
    turns_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    final_answer: str | None = None
    pending_approval: PendingApproval | None = None
    stream_url: str


class SSEEventPayload(BaseModel):
    """JSON data payload serialized inside each SSE frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int | None = None
    session_id: str
    step: int
    sequence: int
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    token_usage: TokenUsage | None = None


class ReplayResponse(BaseModel):
    """Response schema for GET /tasks/{id}/replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    status: SessionStatus | None
    total_steps: int
    total_input_tokens: int
    total_output_tokens: int
    entries: list[dict[str, Any]]
    rendered_text: str
