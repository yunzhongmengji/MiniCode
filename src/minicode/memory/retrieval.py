"""Scoped retrieval of relevant memories."""

import re
import time
from collections.abc import (
    Callable,
    Sequence,
)
from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from minicode.memory.records import (
    MemoryRecord,
    MemoryScope,
)
from minicode.memory.store import (
    MemoryStore,
)

_TOKEN_SEPARATOR = re.compile(r"[\W_]+")


def _tokenize(
    text: str,
) -> frozenset[str]:
    """Normalize text into searchable words."""
    return frozenset(
        token for token in _TOKEN_SEPARATOR.split(text.casefold()) if token
    )


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


@dataclass(frozen=True, slots=True)
class RankedMemory:
    """One relevant memory and its score."""

    record: MemoryRecord
    score: int


class MemoryRetriever(Protocol):
    """Retrieve relevant memories for one task."""

    def retrieve(
        self,
        *,
        query: str,
        scopes: Sequence[MemoryScope],
    ) -> tuple[RankedMemory, ...]:
        """Return relevant active memories."""
        ...


class KeywordMemoryRetriever:
    """Retrieve memories using shared words."""

    def __init__(
        self,
        *,
        store: MemoryStore,
        max_results: int = 5,
        clock: Callable[[], float] = (time.time),
    ) -> None:
        if type(max_results) is not int:
            raise TypeError("max_results must be an integer")

        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

        self._store = store
        self._max_results = max_results
        self._clock = clock

    def retrieve(
        self,
        *,
        query: str,
        scopes: Sequence[MemoryScope],
    ) -> tuple[RankedMemory, ...]:
        """Return globally ranked memories in allowed scopes."""
        scope_snapshot = tuple(scopes)

        for scope in scope_snapshot:
            if not isinstance(
                scope,
                MemoryScope,
            ):
                raise TypeError("scopes must contain MemoryScope instances")

        query_tokens = _tokenize(query)
        now = _read_clock(self._clock)
        candidates: list[RankedMemory] = []

        for scope in scope_snapshot:
            for record in self._store.find(scope):
                if record.is_expired(now=now):
                    continue

                score = len(query_tokens & _tokenize(record.content))

                if score == 0:
                    continue

                candidates.append(
                    RankedMemory(
                        record=record,
                        score=score,
                    )
                )

        ranked = sorted(
            candidates,
            key=lambda candidate: -candidate.score,
        )

        return tuple(ranked[: self._max_results])
