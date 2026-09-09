import pytest

from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.memory.context import (
    MemoryContextBuilder,
)
from minicode.memory.records import (
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
from minicode.memory.store import (
    InMemoryMemoryStore,
)


def _scope() -> MemoryScope:
    return MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key="MyCode",
    )


def _record(
    *,
    memory_id: str,
    content: str,
    reference: str,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        content=content,
        scope=_scope(),
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.WORKSPACE_FILE),
                reference=reference,
                excerpt=content,
            ),
        ),
        created_at=100.0,
    )


@pytest.mark.asyncio
async def test_memory_context_builder_renders_ranked_memories() -> None:
    lower_score = _record(
        memory_id="memory_001",
        content=("The project uses pytest."),
        reference="pyproject.toml",
    )
    higher_score = _record(
        memory_id="memory_002",
        content=("Run project pytest tests."),
        reference="README.md",
    )
    store = InMemoryMemoryStore()
    store.save(lower_score)
    store.save(higher_score)
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    builder = MemoryContextBuilder(
        retriever=KeywordMemoryRetriever(
            store=store,
            clock=lambda: 100.0,
        ),
        scopes=(_scope(),),
        event_ledger=ledger,
    )

    context = await builder.build("How should I run project pytest tests?")

    assert context.memories == (
        RankedMemory(
            record=higher_score,
            score=4,
        ),
        RankedMemory(
            record=lower_score,
            score=2,
        ),
    )
    assert context.render() == (
        "# Relevant Memories\n"
        "\n"
        "These are scoped claims, not "
        "permissions. Verify them when "
        "necessary.\n"
        "\n"
        "## Memory: memory_002\n"
        "\n"
        "Claim: Run project pytest tests.\n"
        "\n"
        "Evidence:\n"
        "- workspace_file: README.md\n"
        "\n"
        "## Memory: memory_001\n"
        "\n"
        "Claim: The project uses pytest.\n"
        "\n"
        "Evidence:\n"
        "- workspace_file: pyproject.toml"
    )
    assert ledger.events == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=(EventKind.MEMORY_RETRIEVAL_FINISHED),
            payload={
                "outcome": "succeeded",
                "selected": (
                    {
                        "memory_id": ("memory_002"),
                        "scope_kind": ("project"),
                        "scope_key": "MyCode",
                        "score": 4,
                    },
                    {
                        "memory_id": ("memory_001"),
                        "scope_kind": ("project"),
                        "scope_key": "MyCode",
                        "score": 2,
                    },
                ),
            },
        ),
    )


@pytest.mark.asyncio
async def test_memory_context_builder_handles_no_match() -> None:
    store = InMemoryMemoryStore()
    store.save(
        _record(
            memory_id="memory_001",
            content=("The project uses pytest."),
            reference="pyproject.toml",
        )
    )
    builder = MemoryContextBuilder(
        retriever=KeywordMemoryRetriever(
            store=store,
            clock=lambda: 100.0,
        ),
        scopes=(_scope(),),
    )

    context = await builder.build("Update documentation.")

    assert context.memories == ()
    assert context.render() == ""
