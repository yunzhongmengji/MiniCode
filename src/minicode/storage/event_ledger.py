"""SQLite-backed append-only Event Ledger."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from minicode.schemas.checkpoints import SessionStatus
from minicode.schemas.events import EventType, LedgerEvent, LedgerEventInput
from minicode.schemas.messages import TokenUsage
from minicode.storage.database import SqliteDatabase


class EventLedger(Protocol):
    """Append-only durable audit ledger for agent sessions."""

    def append(
        self,
        *,
        session_id: str,
        step: int,
        event: LedgerEventInput,
    ) -> LedgerEvent:
        """Persist one event and return it with assigned sequence."""
        ...

    def list_events(self, session_id: str) -> tuple[LedgerEvent, ...]:
        """Return all events for a session ordered by sequence ascending."""
        ...

    def get_event(
        self,
        event_id: int,
        *,
        session_id: str | None = None,
    ) -> LedgerEvent | None:
        """Fetch one event by its persisted event_id, optionally scoped to session_id."""
        ...


class SqliteEventLedger:
    """SQLite implementation of the append-only Event Ledger."""

    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    def latest_sequence(
        self,
        session_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Return the highest persisted sequence number for a session (0 if none)."""
        active_conn = self._db.connection if conn is None else conn
        row = active_conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS max_seq FROM events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["max_seq"]) if row is not None else 0

    def append_in_tx(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        step: int,
        events: Sequence[LedgerEventInput],
    ) -> tuple[LedgerEvent, ...]:
        """Append one or more events inside an existing SQLite transaction."""
        if not events:
            return ()

        now_iso = events[0].timestamp.isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions (session_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, SessionStatus.RUNNING.value, now_iso, now_iso),
        )

        next_seq = self.latest_sequence(session_id, conn=conn) + 1
        recorded: list[LedgerEvent] = []
        for item in events:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    session_id,
                    step,
                    sequence,
                    event_type,
                    payload_json,
                    timestamp,
                    token_usage_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    step,
                    next_seq,
                    item.event_type.value,
                    json.dumps(item.payload, ensure_ascii=False, sort_keys=True),
                    item.timestamp.isoformat(),
                    (
                        item.token_usage.model_dump_json()
                        if item.token_usage is not None
                        else None
                    ),
                ),
            )
            event = LedgerEvent(
                event_id=cursor.lastrowid,
                session_id=session_id,
                step=step,
                sequence=next_seq,
                event_type=item.event_type,
                payload=item.payload,
                timestamp=item.timestamp,
                token_usage=item.token_usage,
            )
            recorded.append(event)
            next_seq += 1

        return tuple(recorded)

    def append(
        self,
        *,
        session_id: str,
        step: int,
        event: LedgerEventInput,
    ) -> LedgerEvent:
        """Persist a single event in its own transaction."""
        with self._db.transaction() as conn:
            recorded = self.append_in_tx(
                conn,
                session_id=session_id,
                step=step,
                events=(event,),
            )
        return recorded[0]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> LedgerEvent:
        token_usage_raw = row["token_usage_json"]
        token_usage = (
            TokenUsage.model_validate_json(token_usage_raw)
            if token_usage_raw is not None
            else None
        )
        return LedgerEvent(
            event_id=int(row["id"]),
            session_id=str(row["session_id"]),
            step=int(row["step"]),
            sequence=int(row["sequence"]),
            event_type=EventType(str(row["event_type"])),
            payload=json.loads(str(row["payload_json"])),
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
            token_usage=token_usage,
        )

    def get_event(
        self,
        event_id: int,
        *,
        session_id: str | None = None,
    ) -> LedgerEvent | None:
        """Fetch a single event by its primary key id, optionally scoped to session_id."""
        if session_id is None:
            row = self._db.connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    step,
                    sequence,
                    event_type,
                    payload_json,
                    timestamp,
                    token_usage_json
                FROM events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        else:
            row = self._db.connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    step,
                    sequence,
                    event_type,
                    payload_json,
                    timestamp,
                    token_usage_json
                FROM events
                WHERE id = ? AND session_id = ?
                """,
                (event_id, session_id),
            ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def list_events(self, session_id: str) -> tuple[LedgerEvent, ...]:
        """Read all persisted events for a session in chronological sequence order."""
        rows = self._db.connection.execute(
            """
            SELECT
                id,
                session_id,
                step,
                sequence,
                event_type,
                payload_json,
                timestamp,
                token_usage_json
            FROM events
            WHERE session_id = ?
            ORDER BY sequence ASC
            """,
            (session_id,),
        ).fetchall()
        return tuple(self._row_to_event(row) for row in rows)
