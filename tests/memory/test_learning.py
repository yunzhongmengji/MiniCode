import pytest

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import (
    ModelResponse,
)
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.memory.evidence import (
    MemoryEvidenceVerificationError,
    RunEvidenceVerifier,
)
from minicode.memory.extraction import (
    MemoryExtractionRequest,
    ScriptedMemoryExtractor,
)
from minicode.memory.learning import (
    MemoryLearner,
    MemoryScopeMismatchError,
)
from minicode.memory.records import (
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryProposal,
    MemoryScope,
    MemoryScopeKind,
)
from minicode.memory.service import (
    MemoryService,
    MemoryWriteOutcome,
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


def _proposal(
    *,
    scope: MemoryScope,
    content: str,
    excerpt: str = ('requires-python = ">=3.12"'),
) -> MemoryProposal:
    return MemoryProposal(
        content=content,
        scope=scope,
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.USER_MESSAGE),
                reference=("run_001:message_001"),
                excerpt=("Inspect the Python version."),
            ),
            MemoryEvidence(
                kind=(MemoryEvidenceKind.TOOL_RESULT),
                reference="run_001:call_001",
                excerpt=excerpt,
            ),
        ),
    )


def _request(
    scope: MemoryScope,
) -> MemoryExtractionRequest:
    return MemoryExtractionRequest(
        run_id="run_001",
        scope=scope,
        message_history=(
            Message(
                role=MessageRole.USER,
                content=("Inspect the Python version."),
            ),
            ToolCall(
                call_id="call_001",
                name="read_file",
                arguments={
                    "path": "pyproject.toml",
                },
            ),
            ToolResult(
                call_id="call_001",
                output=('requires-python = ">=3.12"'),
            ),
        ),
        response=ModelResponse(
            content=("The project requires Python 3.12."),
        ),
    )


@pytest.mark.asyncio
async def test_memory_learner_extracts_and_saves_candidates() -> None:
    scope = _scope("MyCode")
    proposal = _proposal(
        scope=scope,
        content=("This repository requires Python 3.12."),
    )
    request = _request(scope)
    extractor = ScriptedMemoryExtractor(
        candidates=(proposal,),
    )
    store = InMemoryMemoryStore()
    service = MemoryService(
        store=store,
        clock=lambda: 100.0,
        memory_id_factory=(lambda: "memory_001"),
    )
    learner = MemoryLearner(
        extractor=extractor,
        evidence_verifier=(RunEvidenceVerifier()),
        service=service,
    )

    result = await learner.learn(
        request,
        ttl_seconds=30.0,
    )

    assert extractor.requests == (request,)
    assert result.proposals == (proposal,)
    assert result.candidates[0].content == (proposal.content)
    assert result.candidates[0].evidence == (proposal.evidence)
    assert result.writes[0].outcome is (MemoryWriteOutcome.SAVED)
    assert store.get("memory_001") is result.writes[0].record
    assert result.writes[0].record.expires_at == 130.0


@pytest.mark.asyncio
async def test_memory_learner_rejects_fabricated_evidence_before_writing() -> None:
    scope = _scope("MyCode")
    proposal = _proposal(
        scope=scope,
        content=("This repository requires Python 2.7."),
        excerpt=('requires-python = ">=2.7"'),
    )
    store = InMemoryMemoryStore()
    learner = MemoryLearner(
        extractor=ScriptedMemoryExtractor(
            candidates=(proposal,),
        ),
        evidence_verifier=(RunEvidenceVerifier()),
        service=MemoryService(
            store=store,
            clock=lambda: 100.0,
            memory_id_factory=(lambda: "memory_001"),
        ),
    )

    with pytest.raises(
        MemoryEvidenceVerificationError,
        match=("memory evidence excerpt does not match source"),
    ):
        await learner.learn(_request(scope))

    assert store.find(scope) == ()


@pytest.mark.asyncio
async def test_memory_learner_rejects_scope_mismatch_before_writing() -> None:
    request_scope = _scope("MyCode")
    proposal_scope = _scope("OtherProject")
    store = InMemoryMemoryStore()
    learner = MemoryLearner(
        extractor=ScriptedMemoryExtractor(
            candidates=(
                _proposal(
                    scope=proposal_scope,
                    content=("Use Python 3.12."),
                ),
            ),
        ),
        evidence_verifier=(RunEvidenceVerifier()),
        service=MemoryService(
            store=store,
            clock=lambda: 100.0,
        ),
    )

    with pytest.raises(
        MemoryScopeMismatchError,
    ):
        await learner.learn(_request(request_scope))

    assert store.find(proposal_scope) == ()
