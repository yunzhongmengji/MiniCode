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


def _scope(
    project: str,
) -> MemoryScope:
    return MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key=project,
    )


def _user_scope(
    user: str,
) -> MemoryScope:
    return MemoryScope(
        kind=MemoryScopeKind.USER,
        key=user,
    )


def _record(
    *,
    memory_id: str,
    project: str,
    content: str,
    expires_at: float | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        content=content,
        scope=_scope(project),
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.USER_MESSAGE),
                reference="run_001:message_001",
                excerpt=content,
            ),
        ),
        created_at=100.0,
        expires_at=expires_at,
    )


def _scoped_record(
    *,
    memory_id: str,
    scope: MemoryScope,
    content: str,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        content=content,
        scope=scope,
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.USER_MESSAGE),
                reference="run_001:message_001",
                excerpt=content,
            ),
        ),
        created_at=100.0,
    )


def test_memory_retriever_filters_scope_and_expiration_before_ranking() -> None:
    lower_score = _record(
        memory_id="memory_001",
        project="MyCode",
        content=("The project uses pytest."),
    )
    higher_score = _record(
        memory_id="memory_002",
        project="MyCode",
        content=("Run project pytest tests."),
    )
    expired = _record(
        memory_id="memory_003",
        project="MyCode",
        content=("Run project pytest tests with tox."),
        expires_at=105.0,
    )
    foreign = _record(
        memory_id="memory_004",
        project="OtherProject",
        content=("Run project pytest tests."),
    )
    store = InMemoryMemoryStore()

    for record in (
        lower_score,
        higher_score,
        expired,
        foreign,
    ):
        store.save(record)

    retriever = KeywordMemoryRetriever(
        store=store,
        clock=lambda: 110.0,
    )

    results = retriever.retrieve(
        query=("How should I run the project pytest tests?"),
        scopes=(_scope("MyCode"),),
    )

    assert results == (
        RankedMemory(
            record=higher_score,
            score=4,
        ),
        RankedMemory(
            record=lower_score,
            score=3,
        ),
    )


def test_memory_retriever_limits_results_and_handles_no_match() -> None:
    first = _record(
        memory_id="memory_001",
        project="MyCode",
        content="Use pytest for tests.",
    )
    second = _record(
        memory_id="memory_002",
        project="MyCode",
        content="Run pytest locally.",
    )
    store = InMemoryMemoryStore()
    store.save(first)
    store.save(second)

    retriever = KeywordMemoryRetriever(
        store=store,
        max_results=1,
        clock=lambda: 100.0,
    )

    matches = retriever.retrieve(
        query="Use pytest for tests.",
        scopes=(_scope("MyCode"),),
    )
    no_matches = retriever.retrieve(
        query="Update documentation.",
        scopes=(_scope("MyCode"),),
    )

    assert matches == (
        RankedMemory(
            record=first,
            score=4,
        ),
    )
    assert no_matches == ()


def test_memory_retriever_applies_one_limit_across_scopes() -> None:
    project_memory = _scoped_record(
        memory_id="memory_001",
        scope=_scope("MyCode"),
        content="Use pytest.",
    )
    user_memory = _scoped_record(
        memory_id="memory_002",
        scope=_user_scope("songshihao"),
        content=("Prefer pytest test explanations."),
    )
    store = InMemoryMemoryStore()
    store.save(project_memory)
    store.save(user_memory)

    retriever = KeywordMemoryRetriever(
        store=store,
        max_results=1,
        clock=lambda: 100.0,
    )

    results = retriever.retrieve(
        query=("Explain the pytest test."),
        scopes=(
            _scope("MyCode"),
            _user_scope("songshihao"),
        ),
    )

    assert results == (
        RankedMemory(
            record=user_memory,
            score=2,
        ),
    )
