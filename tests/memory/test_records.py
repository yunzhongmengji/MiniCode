import pytest

from minicode.memory.records import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeKind,
)


def _project_scope() -> MemoryScope:
    return MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key="MyCode",
    )


def _python_evidence() -> MemoryEvidence:
    return MemoryEvidence(
        kind=(MemoryEvidenceKind.WORKSPACE_FILE),
        reference="pyproject.toml",
        excerpt=('requires-python = ">=3.12"'),
    )


def test_memory_candidate_snapshots_scoped_evidence() -> None:
    evidence = [
        _python_evidence(),
    ]

    candidate = MemoryCandidate(
        content=("This repository requires Python 3.12."),
        scope=_project_scope(),
        evidence=evidence,
    )

    evidence.clear()

    assert candidate.scope == (_project_scope())
    assert candidate.evidence == (_python_evidence(),)


def test_memory_candidate_requires_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="memory must contain evidence",
    ):
        MemoryCandidate(
            content=("This repository requires Python 3.12."),
            scope=_project_scope(),
            evidence=(),
        )


def test_memory_record_expires_at_boundary() -> None:
    record = MemoryRecord(
        memory_id="memory_001",
        content=("This repository requires Python 3.12."),
        scope=_project_scope(),
        evidence=(_python_evidence(),),
        created_at=100.0,
        expires_at=110.0,
    )

    assert (
        record.is_expired(
            now=109.99,
        )
        is False
    )
    assert (
        record.is_expired(
            now=110.0,
        )
        is True
    )


def test_memory_expiration_must_follow_creation() -> None:
    with pytest.raises(
        ValueError,
        match=("expires_at must be later than created_at"),
    ):
        MemoryRecord(
            memory_id="memory_001",
            content="Repository convention.",
            scope=_project_scope(),
            evidence=(_python_evidence(),),
            created_at=100.0,
            expires_at=100.0,
        )
