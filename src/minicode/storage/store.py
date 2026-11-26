"""Atomic unit-of-work coordinator for SQLite Event Ledger and Checkpoint Store."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from minicode.schemas.checkpoints import SessionCheckpoint
from minicode.schemas.events import EventType, LedgerEvent, LedgerEventInput
from minicode.storage.checkpoint_store import SqliteCheckpointStore
from minicode.storage.database import SqliteDatabase
from minicode.storage.event_ledger import SqliteEventLedger

EventListener = Callable[[tuple[LedgerEvent, ...]], None]


class SqliteRuntimeStorage:
    """Coordinate atomic persistence of checkpoints and ledger events."""

    def __init__(self, db_path: Path | str) -> None:
        self._db = SqliteDatabase(db_path)
        self._event_ledger = SqliteEventLedger(self._db)
        self._checkpoint_store = SqliteCheckpointStore(self._db)
        self._listeners: list[EventListener] = []

    def add_event_listener(self, listener: EventListener) -> None:
        """Register a callback invoked after events are durably committed."""
        self._listeners.append(listener)

    def remove_event_listener(self, listener: EventListener) -> None:
        """Unregister a previously added commit listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def database(self) -> SqliteDatabase:
        """Return the underlying SQLite database manager."""
        return self._db

    @property
    def event_ledger(self) -> SqliteEventLedger:
        """Return the SQLite event ledger."""
        return self._event_ledger

    @property
    def checkpoint_store(self) -> SqliteCheckpointStore:
        """Return the SQLite checkpoint store."""
        return self._checkpoint_store

    def commit_step(
        self,
        *,
        checkpoint: SessionCheckpoint,
        events: Sequence[LedgerEventInput] = (),
        record_checkpoint_event: bool = True,
    ) -> tuple[LedgerEvent, ...]:
        """Atomically persist step events and checkpoint in one SQLite transaction."""
        events_to_write = list(events)
        if record_checkpoint_event:
            events_to_write.append(
                LedgerEventInput(
                    event_type=EventType.CHECKPOINT_SAVED,
                    payload={
                        "step": checkpoint.step,
                        "status": checkpoint.status.value,
                        "turns_used": checkpoint.turns_used,
                        "tool_calls_used": checkpoint.tool_calls_used,
                        "history_items": len(checkpoint.history),
                        "pending_tool_calls": len(checkpoint.pending_tool_calls),
                    },
                    timestamp=checkpoint.created_at,
                )
            )

        with self._db.transaction() as conn:
            self._checkpoint_store.save_in_tx(conn, checkpoint)
            recorded = self._event_ledger.append_in_tx(
                conn,
                session_id=checkpoint.session_id,
                step=checkpoint.step,
                events=events_to_write,
            )
        if recorded:
            for listener in tuple(self._listeners):
                listener(recorded)
        return recorded

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._db.close()
