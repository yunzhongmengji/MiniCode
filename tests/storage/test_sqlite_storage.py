"""Tests for SQLite Event Ledger, Checkpoint Store, and atomic transactions."""

from __future__ import annotations

from pathlib import Path

import pytest

from minicode.schemas import (
    EventType,
    LedgerEventInput,
    MessageRecord,
    MessageRole,
    SessionCheckpoint,
    SessionStatus,
    TokenUsage,
)
from minicode.storage import SqliteRuntimeStorage


def test_sqlite_commit_step_persists_checkpoint_and_events_atomically(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.sqlite3"
    storage = SqliteRuntimeStorage(db_path)
    try:
        checkpoint = SessionCheckpoint(
            session_id="sess_atomic_1",
            step=1,
            status=SessionStatus.RUNNING,
            history=(MessageRecord(role=MessageRole.USER, content="fix bug"),),
            turns_used=1,
            total_input_tokens=120,
            total_output_tokens=45,
        )
        events = storage.commit_step(
            checkpoint=checkpoint,
            events=(
                LedgerEventInput(
                    event_type=EventType.REASONING_COMPLETED,
                    payload={"turn": 1, "thinking": "inspecting repo"},
                    token_usage=TokenUsage(input_tokens=120, output_tokens=45),
                ),
            ),
        )
        assert [event.sequence for event in events] == [1, 2]
        assert events[0].event_type is EventType.REASONING_COMPLETED
        assert events[0].token_usage == TokenUsage(input_tokens=120, output_tokens=45)
        assert events[1].event_type is EventType.CHECKPOINT_SAVED
    finally:
        storage.close()

    # Re-open from a fresh connection to verify durability across restarts.
    reopened = SqliteRuntimeStorage(db_path)
    try:
        loaded = reopened.checkpoint_store.load_latest("sess_atomic_1")
        assert loaded is not None
        assert loaded.session_id == "sess_atomic_1"
        assert loaded.step == 1
        assert loaded.total_input_tokens == 120
        assert loaded.total_output_tokens == 45

        persisted_events = reopened.event_ledger.list_events("sess_atomic_1")
        assert len(persisted_events) == 2
        assert persisted_events[0].token_usage is not None
        assert persisted_events[0].token_usage.total_tokens == 165
    finally:
        reopened.close()


def test_sqlite_transaction_rolls_back_all_writes_on_error(tmp_path: Path) -> None:
    db_path = tmp_path / "rollback.sqlite3"
    storage = SqliteRuntimeStorage(db_path)
    try:
        checkpoint = SessionCheckpoint(
            session_id="sess_rollback",
            step=0,
            status=SessionStatus.RUNNING,
        )
        with (
            pytest.raises(RuntimeError, match="simulated disk failure"),
            storage.database.transaction() as conn,
        ):
            storage.checkpoint_store.save_in_tx(conn, checkpoint)
            storage.event_ledger.append_in_tx(
                conn,
                session_id="sess_rollback",
                step=0,
                events=(
                    LedgerEventInput(
                        event_type=EventType.SESSION_STARTED,
                        payload={"task": "will rollback"},
                    ),
                ),
            )
            raise RuntimeError("simulated disk failure")

        assert storage.checkpoint_store.load_latest("sess_rollback") is None
        assert storage.event_ledger.list_events("sess_rollback") == ()
    finally:
        storage.close()
