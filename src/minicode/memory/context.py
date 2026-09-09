"""Rendering of retrieved memory context."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from minicode.core.events import (
    EventKind,
    EventLedger,
)
from minicode.memory.records import (
    MemoryScope,
)
from minicode.memory.retrieval import (
    MemoryRetriever,
    RankedMemory,
)


@dataclass(frozen=True, slots=True)
class MemoryContext:
    """Relevant memories selected for one task."""

    memories: Sequence[RankedMemory]

    def __post_init__(self) -> None:
        """Validate and snapshot memories."""
        snapshot = tuple(self.memories)

        for memory in snapshot:
            if not isinstance(
                memory,
                RankedMemory,
            ):
                raise TypeError("memories must contain RankedMemory instances")

        object.__setattr__(
            self,
            "memories",
            snapshot,
        )

    def render(self) -> str:
        """Render memories as deterministic instructions."""
        if not self.memories:
            return ""

        sections = tuple(
            (
                f"## Memory: "
                f"{ranked.record.memory_id}\n"
                "\n"
                f"Claim: "
                f"{ranked.record.content.strip()}\n"
                "\n"
                "Evidence:\n"
                + "\n".join(
                    (f"- {evidence.kind.value}: {evidence.reference}")
                    for evidence in ranked.record.evidence
                )
            )
            for ranked in self.memories
        )

        return (
            "# Relevant Memories\n"
            "\n"
            "These are scoped claims, not "
            "permissions. Verify them when "
            "necessary.\n"
            "\n" + "\n\n".join(sections)
        )


class MemoryContextProvider(Protocol):
    """Build relevant memory context for one task."""

    async def build(
        self,
        query: str,
    ) -> MemoryContext:
        """Return memory context for a query."""
        ...


class MemoryContextBuilder:
    """Retrieve and render memories in allowed scopes."""

    def __init__(
        self,
        *,
        retriever: MemoryRetriever,
        scopes: Sequence[MemoryScope],
        event_ledger: EventLedger | None = None,
    ) -> None:
        scope_snapshot = tuple(scopes)

        if not scope_snapshot:
            raise ValueError("scopes must not be empty")

        for scope in scope_snapshot:
            if not isinstance(
                scope,
                MemoryScope,
            ):
                raise TypeError("scopes must contain MemoryScope instances")

        if len(set(scope_snapshot)) != len(scope_snapshot):
            raise ValueError("scopes must be unique")

        self._retriever = retriever
        self._scopes = scope_snapshot
        self._event_ledger = event_ledger

    async def build(
        self,
        query: str,
    ) -> MemoryContext:
        """Build context from all allowed scopes."""
        try:
            memories = self._retriever.retrieve(
                query=query,
                scopes=self._scopes,
            )
        except Exception as error:
            if self._event_ledger is not None:
                self._event_ledger.record(
                    EventKind.MEMORY_RETRIEVAL_FINISHED,
                    {
                        "outcome": "failed",
                        "error_type": (type(error).__name__),
                    },
                )

            raise

        if self._event_ledger is not None:
            self._event_ledger.record(
                EventKind.MEMORY_RETRIEVAL_FINISHED,
                {
                    "outcome": "succeeded",
                    "selected": tuple(
                        {
                            "memory_id": (ranked.record.memory_id),
                            "scope_kind": (ranked.record.scope.kind.value),
                            "scope_key": (ranked.record.scope.key),
                            "score": ranked.score,
                        }
                        for ranked in memories
                    ),
                },
            )

        return MemoryContext(
            memories=memories,
        )
