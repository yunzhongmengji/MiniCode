"""Pydantic v2 schemas for checkpoints, risk levels, and approval state."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from minicode.schemas.events import utc_now
from minicode.schemas.messages import HistoryEntry, ToolCallRecord


class SessionStatus(StrEnum):
    """Lifecycle status of an agent session."""

    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class RiskLevel(StrEnum):
    """Risk classification for tools."""

    READ_ONLY = "read_only"
    WRITE_FILE = "write_file"
    EXECUTE_SHELL = "execute_shell"


class ApprovalDecision(StrEnum):
    """External human/caller decision for a gated high-risk tool call."""

    APPROVE = "approve"
    REJECT = "reject"


class PendingApproval(BaseModel):
    """Exact high-risk tool call awaiting external approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel
    reason: str = Field(min_length=1)


class SessionCheckpoint(BaseModel):
    """Durable, versioned snapshot of a session at a specific step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    session_id: str = Field(min_length=1)
    step: int = Field(ge=0)
    status: SessionStatus
    history: tuple[HistoryEntry, ...] = ()
    pending_tool_calls: tuple[ToolCallRecord, ...] = ()
    pending_approval: PendingApproval | None = None
    approved_call_ids: tuple[str, ...] = ()
    turns_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    final_answer: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_approval_invariants(self) -> SessionCheckpoint:
        if (
            self.status is SessionStatus.WAITING_APPROVAL
            and self.pending_approval is None
        ):
            raise ValueError(
                "WAITING_APPROVAL checkpoint must include pending_approval"
            )
        if (
            self.status is not SessionStatus.WAITING_APPROVAL
            and self.pending_approval is not None
        ):
            raise ValueError(
                "pending_approval may only be set when status is WAITING_APPROVAL"
            )
        return self
