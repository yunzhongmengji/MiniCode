"""Admission and lifecycle operations for memory."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from uuid import uuid4

from minicode.memory.records import (
    MemoryCandidate,
    MemoryRecord,
)
from minicode.memory.store import (
    MemoryStore,
)


def _default_memory_id() -> str:
    """Generate one unique memory identifier."""
    return f"memory_{uuid4().hex}"


def _normalize_content(
    content: str,
) -> str:
    """Normalize content for exact deduplication."""
    return " ".join(content.casefold().split())


def _read_clock(
    clock: Callable[[], float],
) -> float:
    """Read and validate the current time."""
    value = clock()

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError("clock must return a number")

    normalized = float(value)

    if not isfinite(normalized):
        raise ValueError("clock must return a finite number")

    return normalized


def _normalize_ttl(
    ttl_seconds: float | None,
) -> float | None:
    """Validate an optional memory lifetime."""
    if ttl_seconds is None:
        return None

    if isinstance(
        ttl_seconds,
        bool,
    ) or not isinstance(
        ttl_seconds,
        (int, float),
    ):
        raise TypeError("ttl_seconds must be a number or None")

    normalized = float(ttl_seconds)

    if not isfinite(normalized) or normalized <= 0:
        raise ValueError("ttl_seconds must be finite and greater than zero")

    return normalized


class MemoryWriteOutcome(StrEnum):
    """Possible admission results."""

    SAVED = "saved"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    """Result of admitting one candidate."""

    outcome: MemoryWriteOutcome
    record: MemoryRecord


class MemoryService:
    """Admit candidates into a memory store."""

    def __init__(
        self,
        *,
        store: MemoryStore,
        clock: Callable[[], float] = (time.time),
        memory_id_factory: Callable[
            [],
            str,
        ] = _default_memory_id,
    ) -> None:
        self._store = store
        self._clock = clock
        self._memory_id_factory = memory_id_factory

    def remember(
        self,
        candidate: MemoryCandidate,
        *,
        ttl_seconds: float | None = None,
    ) -> MemoryWriteResult:
        """Save a candidate unless an active duplicate exists."""
        if not isinstance(
            candidate,
            MemoryCandidate,
        ):
            raise TypeError("candidate must be a MemoryCandidate")

        normalized_ttl = _normalize_ttl(ttl_seconds)
        now = _read_clock(self._clock)
        normalized_content = _normalize_content(candidate.content)

        for existing in self._store.find(candidate.scope):
            if existing.is_expired(now=now):
                continue

            if _normalize_content(existing.content) == normalized_content:
                return MemoryWriteResult(
                    outcome=(MemoryWriteOutcome.DUPLICATE),
                    record=existing,
                )

        expires_at = None if normalized_ttl is None else now + normalized_ttl
        record = MemoryRecord(
            memory_id=(self._memory_id_factory()),
            content=candidate.content,
            scope=candidate.scope,
            evidence=candidate.evidence,
            created_at=now,
            expires_at=expires_at,
        )
        self._store.save(record)

        return MemoryWriteResult(
            outcome=MemoryWriteOutcome.SAVED,
            record=record,
        )

    def forget(
        self,
        memory_id: str,
    ) -> MemoryRecord:
        """Delete one stored memory."""
        return self._store.delete(memory_id)
