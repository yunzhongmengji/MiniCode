import pytest

from minicode.memory.records import (
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeKind,
)
from minicode.memory.store import (
    InMemoryMemoryStore,
    MemoryAlreadyExistsError,
)


def _scope(
    key: str,
) -> MemoryScope:
    return MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key=key,
    )


def _record(
    *,
    memory_id: str,
    project: str,
    content: str,
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
    )


def test_memory_store_isolates_scopes_and_preserves_order() -> None:
    first_mycode = _record(
        memory_id="memory_001",
        project="MyCode",
        content="Use Python 3.12.",
    )
    other_project = _record(
        memory_id="memory_002",
        project="OtherProject",
        content="Use Python 3.11.",
    )
    second_mycode = _record(
        memory_id="memory_003",
        project="MyCode",
        content="Run tests with pytest.",
    )
    store = InMemoryMemoryStore()

    store.save(first_mycode)
    store.save(other_project)
    store.save(second_mycode)

    assert store.find(_scope("MyCode")) == (
        first_mycode,
        second_mycode,
    )
    assert store.find(_scope("OtherProject")) == (other_project,)


def test_memory_store_does_not_overwrite_duplicate_id() -> None:
    original = _record(
        memory_id="memory_001",
        project="MyCode",
        content="Use Python 3.12.",
    )
    conflicting = _record(
        memory_id="memory_001",
        project="MyCode",
        content="Use Python 3.10.",
    )
    store = InMemoryMemoryStore()
    store.save(original)

    with pytest.raises(
        MemoryAlreadyExistsError,
        match=("memory already exists: memory_001"),
    ):
        store.save(conflicting)

    assert store.get("memory_001") is original


def test_memory_store_deletes_record() -> None:
    record = _record(
        memory_id="memory_001",
        project="MyCode",
        content="Use Python 3.12.",
    )
    store = InMemoryMemoryStore()
    store.save(record)

    deleted = store.delete("memory_001")

    assert deleted is record
    assert store.get("memory_001") is None
    assert store.find(_scope("MyCode")) == ()
