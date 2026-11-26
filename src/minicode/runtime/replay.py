"""Read-only chronological trajectory replay from the SQLite Event Ledger."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from minicode.runtime.engine import SessionNotFoundError
from minicode.schemas.checkpoints import ApprovalDecision, RiskLevel, SessionStatus
from minicode.schemas.events import EventType, LedgerEvent
from minicode.schemas.messages import TokenUsage
from minicode.storage.store import SqliteRuntimeStorage


class ReplayEntry(BaseModel):
    """One auditable timeline entry reconstructed from a LedgerEvent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=1)
    step: int = Field(ge=0)
    timestamp: datetime
    event_type: EventType
    summary: str
    thinking: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_output: str | None = None
    is_error: bool | None = None
    approval_decision: ApprovalDecision | None = None
    risk_level: RiskLevel | None = None
    token_usage: TokenUsage | None = None


class SessionReplay(BaseModel):
    """Complete read-only audit replay for a persisted session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    status: SessionStatus | None
    total_steps: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    entries: tuple[ReplayEntry, ...]

    def render_text(self) -> str:
        """Render the trajectory into a human-readable audit log."""
        lines = [
            f"Session Replay: {self.session_id}",
            f"Status: {self.status.value if self.status is not None else 'unknown'}",
            (
                f"Total Steps: {self.total_steps} | "
                f"Tokens: in={self.total_input_tokens}, out={self.total_output_tokens}"
            ),
            "-" * 72,
        ]
        for entry in self.entries:
            header = (
                f"[#{entry.sequence} step={entry.step} "
                f"{entry.timestamp.isoformat()}] {entry.event_type.value}: "
                f"{entry.summary}"
            )
            lines.append(header)
            if entry.thinking:
                lines.append(f"  thinking: {entry.thinking}")
            if entry.tool_name is not None:
                args_text = (
                    json.dumps(entry.tool_arguments, ensure_ascii=False, sort_keys=True)
                    if entry.tool_arguments is not None
                    else "{}"
                )
                lines.append(f"  tool: {entry.tool_name}({args_text})")
            if entry.tool_output is not None:
                lines.append(
                    f"  output (is_error={entry.is_error}): {entry.tool_output}"
                )
            if entry.approval_decision is not None:
                lines.append(
                    f"  approval: {entry.approval_decision.value} "
                    f"(risk={entry.risk_level.value if entry.risk_level else 'unknown'})"
                )
            if entry.token_usage is not None:
                lines.append(
                    f"  tokens: in={entry.token_usage.input_tokens}, "
                    f"out={entry.token_usage.output_tokens}, "
                    f"total={entry.token_usage.total_tokens}"
                )
        return "\n".join(lines)


def _event_to_replay_entry(event: LedgerEvent) -> ReplayEntry:
    payload = event.payload
    et = event.event_type

    if et is EventType.SESSION_STARTED:
        task = str(payload.get("task", ""))
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"started task: {task}",
        )

    if et is EventType.SESSION_RESUMED:
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=(
                f"resumed from step {payload.get('resumed_from_step')} "
                f"(pending_tools={payload.get('pending_tool_calls')})"
            ),
        )

    if et is EventType.REASONING_COMPLETED:
        thinking = str(payload.get("thinking", ""))
        tool_calls = payload.get("tool_calls", [])
        tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"turn {payload.get('turn')} proposed {tool_count} tool call(s)",
            thinking=thinking or None,
            token_usage=event.token_usage,
        )

    if et is EventType.APPROVAL_REQUIRED:
        risk_raw = payload.get("risk_level")
        risk = RiskLevel(str(risk_raw)) if risk_raw is not None else None
        args = payload.get("arguments")
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"paused for approval ({payload.get('reason', '')})",
            tool_name=str(payload.get("tool_name", "")),
            tool_arguments=args if isinstance(args, dict) else None,
            risk_level=risk,
        )

    if et is EventType.APPROVAL_DECIDED:
        decision_raw = payload.get("decision")
        decision = (
            ApprovalDecision(str(decision_raw)) if decision_raw is not None else None
        )
        risk_raw = payload.get("risk_level")
        risk = RiskLevel(str(risk_raw)) if risk_raw is not None else None
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"decision={payload.get('decision')} reason={payload.get('reason', '')}",
            tool_name=str(payload.get("tool_name", "")),
            approval_decision=decision,
            risk_level=risk,
        )

    if et is EventType.TOOL_EXECUTED:
        args = payload.get("arguments")
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=(
                f"executed {payload.get('tool_name')} "
                f"(is_error={payload.get('is_error')})"
            ),
            tool_name=str(payload.get("tool_name", "")),
            tool_arguments=args if isinstance(args, dict) else None,
            tool_output=str(payload.get("output", "")),
            is_error=bool(payload.get("is_error", False)),
        )

    if et is EventType.CHECKPOINT_SAVED:
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=(
                f"checkpoint saved (status={payload.get('status')}, "
                f"pending_tools={payload.get('pending_tool_calls')})"
            ),
        )

    if et is EventType.SESSION_PAUSED:
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"paused in status {payload.get('status')}",
        )

    if et is EventType.SESSION_COMPLETED:
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"completed in {payload.get('turns_used')} turn(s)",
        )

    if et is EventType.SESSION_ABORTED:
        return ReplayEntry(
            sequence=event.sequence,
            step=event.step,
            timestamp=event.timestamp,
            event_type=et,
            summary=f"aborted ({payload.get('reason', '')})",
        )

    return ReplayEntry(
        sequence=event.sequence,
        step=event.step,
        timestamp=event.timestamp,
        event_type=et,
        summary=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        token_usage=event.token_usage,
    )


def replay(session_id: str, storage: SqliteRuntimeStorage) -> SessionReplay:
    """Read-only chronological replay of a session from the SQLite Event Ledger."""
    events = storage.event_ledger.list_events(session_id)
    if not events:
        raise SessionNotFoundError(f"no events found for session '{session_id}'")

    latest_checkpoint = storage.checkpoint_store.load_latest(session_id)
    entries = tuple(_event_to_replay_entry(event) for event in events)
    total_input = sum(
        event.token_usage.input_tokens
        for event in events
        if event.token_usage is not None
    )
    total_output = sum(
        event.token_usage.output_tokens
        for event in events
        if event.token_usage is not None
    )
    max_step = max(event.step for event in events)

    return SessionReplay(
        session_id=session_id,
        status=latest_checkpoint.status if latest_checkpoint is not None else None,
        total_steps=max_step,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        entries=entries,
    )
