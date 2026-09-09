from minicode.memory.records import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeKind,
)
from minicode.memory.retrieval import (
    KeywordMemoryRetriever,
    RankedMemory,
)
from minicode.memory.service import (
    MemoryService,
    MemoryWriteOutcome,
    MemoryWriteResult,
)
from minicode.memory.store import (
    InMemoryMemoryStore,
)


def _candidate(
    content: str,
) -> MemoryCandidate:
    return MemoryCandidate(
        content=content,
        scope=MemoryScope(
            kind=MemoryScopeKind.PROJECT,
            key="MyCode",
        ),
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.WORKSPACE_FILE),
                reference="pyproject.toml",
                excerpt=content,
            ),
        ),
    )


def test_memory_service_saves_candidate_with_lifecycle() -> None:
    store = InMemoryMemoryStore()
    service = MemoryService(
        store=store,
        clock=lambda: 100.0,
        memory_id_factory=(lambda: "memory_001"),
    )
    candidate = _candidate("Use Python 3.12.")

    result = service.remember(
        candidate,
        ttl_seconds=30.0,
    )

    expected_record = MemoryRecord(
        memory_id="memory_001",
        content="Use Python 3.12.",
        scope=candidate.scope,
        evidence=candidate.evidence,
        created_at=100.0,
        expires_at=130.0,
    )
    assert result == MemoryWriteResult(
        outcome=MemoryWriteOutcome.SAVED,
        record=expected_record,
    )
    assert store.get("memory_001") == expected_record


def test_memory_service_returns_active_duplicate() -> None:
    clock_values = iter(
        (
            100.0,
            101.0,
        )
    )
    store = InMemoryMemoryStore()
    service = MemoryService(
        store=store,
        clock=lambda: next(clock_values),
        memory_id_factory=(lambda: "memory_001"),
    )

    first = service.remember(_candidate("Use Python 3.12."))
    duplicate = service.remember(_candidate("  use   PYTHON 3.12.  "))

    assert first.outcome is (MemoryWriteOutcome.SAVED)
    assert duplicate == (
        MemoryWriteResult(
            outcome=(MemoryWriteOutcome.DUPLICATE),
            record=first.record,
        )
    )
    assert store.find(first.record.scope) == (first.record,)


def test_expired_memory_does_not_block_refresh() -> None:
    clock_values = iter(
        (
            100.0,
            111.0,
        )
    )
    memory_ids = iter(
        (
            "memory_001",
            "memory_002",
        )
    )
    store = InMemoryMemoryStore()
    service = MemoryService(
        store=store,
        clock=lambda: next(clock_values),
        memory_id_factory=lambda: next(memory_ids),
    )

    expired = service.remember(
        _candidate("Use Python 3.12."),
        ttl_seconds=10.0,
    )
    refreshed = service.remember(
        _candidate("use python 3.12."),
        ttl_seconds=10.0,
    )

    assert refreshed.outcome is (MemoryWriteOutcome.SAVED)
    assert refreshed.record.memory_id == ("memory_002")
    assert store.find(refreshed.record.scope) == (
        expired.record,
        refreshed.record,
    )


def test_wrong_memory_can_be_removed_and_replaced() -> None:
    clock_values = iter(
        (
            100.0,
            101.0,
        )
    )
    memory_ids = iter(
        (
            "memory_001",
            "memory_002",
        )
    )
    store = InMemoryMemoryStore()
    service = MemoryService(
        store=store,
        clock=lambda: next(clock_values),
        memory_id_factory=lambda: next(memory_ids),
    )

    wrong = service.remember(_candidate("This repository requires Python 3.10."))

    retriever = KeywordMemoryRetriever(
        store=store,
        clock=lambda: 102.0,
    )
    query = "Which Python version does this repository require?"
    scopes = (wrong.record.scope,)

    assert retriever.retrieve(
        query=query,
        scopes=scopes,
    ) == (
        RankedMemory(
            record=wrong.record,
            score=3,
        ),
    )

    deleted = service.forget(wrong.record.memory_id)
    corrected = service.remember(_candidate("This repository requires Python 3.12."))

    assert deleted is wrong.record
    assert store.get("memory_001") is None
    assert corrected.outcome is (MemoryWriteOutcome.SAVED)
    assert corrected.record.memory_id == ("memory_002")

    assert retriever.retrieve(
        query=query,
        scopes=scopes,
    ) == (
        RankedMemory(
            record=corrected.record,
            score=3,
        ),
    )
