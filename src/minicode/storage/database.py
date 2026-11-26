"""SQLite connection and schema lifecycle management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    token_usage_json TEXT,
    UNIQUE(session_id, sequence),
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_session_seq
    ON events(session_id, sequence);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session_id
    ON checkpoints(session_id, id DESC);
"""


class SqliteDatabase:
    """Manage a SQLite database with explicit ACID transactions."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None enables explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK.
        self._conn = sqlite3.connect(
            self._path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self.initialize()

    @property
    def path(self) -> str:
        """Return the configured SQLite database path."""
        return self._path

    def _configure_connection(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL;")

    def initialize(self) -> None:
        """Ensure required tables and indexes exist."""
        with self.transaction() as conn:
            for statement in _SCHEMA_SQL.strip().split(";"):
                sql = statement.strip()
                if sql:
                    conn.execute(sql)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Execute a block inside an atomic BEGIN IMMEDIATE transaction."""
        if self._conn.in_transaction:
            yield self._conn
            return

        self._conn.execute("BEGIN IMMEDIATE;")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK;")
            raise
        else:
            self._conn.execute("COMMIT;")

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the underlying connection for read queries."""
        return self._conn

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
