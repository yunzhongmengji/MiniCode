"""Pydantic v2 schemas for the persistent SQLite Event Ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from minicode.schemas.messages import TokenUsage


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class EventType(StrEnum):
    """Ordered audit event types recorded for every agent session."""

    SESSION_STARTED = "session_started"
    SESSION_RESUMED = "session_resumed"
    REASONING_COMPLETED = "reasoning_completed"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECIDED = "approval_decided"
    TOOL_EXECUTED = "tool_executed"
    CHECKPOINT_SAVED = "checkpoint_saved"
    SESSION_PAUSED = "session_paused"
    SESSION_COMPLETED = "session_completed"
    SESSION_ABORTED = "session_aborted"
    SESSION_FAILED = "session_failed"


class LedgerEventInput(BaseModel):
    """Event data provided before sequence assignment by the ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    token_usage: TokenUsage | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class LedgerEvent(BaseModel):
    """One immutable, sequenced event persisted in the SQLite Event Ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int | None = Field(default=None, ge=1)
    session_id: str = Field(min_length=1)
    step: int = Field(ge=0)
    sequence: int = Field(ge=1)
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
    token_usage: TokenUsage | None = None
