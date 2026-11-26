"""SQLite-backed durable Checkpoint Store."""

from __future__ import annotations

import sqlite3
from typing import Protocol

from minicode.schemas.checkpoints import SessionCheckpoint
from minicode.storage.database import SqliteDatabase


class CheckpointStore(Protocol):
    """Durable storage for session checkpoints."""

    def save(self, checkpoint: SessionCheckpoint) -> None:
        """Persist a checkpoint snapshot."""
        ...

    def load_latest(self, session_id: str) -> SessionCheckpoint | None:
        """Load the most recent checkpoint for a session, or None if missing."""
        ...

    def list_checkpoints(self, session_id: str) -> tuple[SessionCheckpoint, ...]:
        """List all checkpoints for a session in creation order."""
        ...


class SqliteCheckpointStore:
    """SQLite implementation of durable session checkpoints."""

    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    def save_in_tx(
        self,
        conn: sqlite3.Connection,
        checkpoint: SessionCheckpoint,
    ) -> None:
        """Persist a checkpoint and synchronize session status inside a transaction."""
        ts = checkpoint.created_at.isoformat()
        conn.execute(
            """
            INSERT INTO sessions (session_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (checkpoint.session_id, checkpoint.status.value, ts, ts),
        )
        conn.execute(
            """
            INSERT INTO checkpoints (session_id, step, status, state_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                checkpoint.session_id,
                checkpoint.step,
                checkpoint.status.value,
                checkpoint.model_dump_json(),
                ts,
            ),
        )

    def save(self, checkpoint: SessionCheckpoint) -> None:
        """Persist a checkpoint in its own atomic transaction."""
        with self._db.transaction() as conn:
            self.save_in_tx(conn, checkpoint)

    def load_latest(self, session_id: str) -> SessionCheckpoint | None:
        """Load the latest checkpoint snapshot for a session."""
        row = self._db.connection.execute(
            """
            SELECT state_json
            FROM checkpoints
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return SessionCheckpoint.model_validate_json(str(row["state_json"]))

    def list_checkpoints(self, session_id: str) -> tuple[SessionCheckpoint, ...]:
        """Return all historical checkpoints for a session in chronological order."""
        rows = self._db.connection.execute(
            """
            SELECT state_json
            FROM checkpoints
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return tuple(
            SessionCheckpoint.model_validate_json(str(row["state_json"]))
            for row in rows
        )
