import pytest

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import (
    ModelResponse,
)
from minicode.memory.extraction import (
    MemoryExtractionRequest,
    ScriptedMemoryExtractor,
)
from minicode.memory.records import (
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryProposal,
    MemoryScope,
    MemoryScopeKind,
)


@pytest.mark.asyncio
async def test_scripted_extractor_proposes_without_saving() -> None:
    scope = MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key="MyCode",
    )
    proposal = MemoryProposal(
        content=("This repository requires Python 3.12."),
        scope=scope,
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.WORKSPACE_FILE),
                reference="pyproject.toml",
                excerpt=('requires-python = ">=3.12"'),
            ),
        ),
    )
    original_history = [
        Message(
            role=MessageRole.USER,
            content=("Inspect the Python version."),
        ),
    ]
    request = MemoryExtractionRequest(
        run_id="run_001",
        scope=scope,
        message_history=original_history,
        response=ModelResponse(
            content=("The project requires Python 3.12."),
        ),
    )
    extractor = ScriptedMemoryExtractor(
        candidates=(proposal,),
    )

    original_history.clear()

    candidates = await extractor.extract(request)

    assert request.message_history == (
        Message(
            role=MessageRole.USER,
            content=("Inspect the Python version."),
        ),
    )
    assert candidates == (proposal,)
    assert extractor.requests == (request,)
