import pytest

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import (
    ModelResponse,
)
from minicode.core.query_loop import (
    QueryLoop,
)
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.memory.context import (
    MemoryContextBuilder,
)
from minicode.memory.evidence import (
    RunEvidenceVerifier,
)
from minicode.memory.extraction import (
    MemoryExtractionRequest,
    ScriptedMemoryExtractor,
)
from minicode.memory.learning import (
    MemoryLearner,
)
from minicode.memory.records import (
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryProposal,
    MemoryScope,
    MemoryScopeKind,
)
from minicode.memory.retrieval import (
    KeywordMemoryRetriever,
)
from minicode.memory.service import (
    MemoryService,
    MemoryWriteOutcome,
)
from minicode.memory.store import (
    InMemoryMemoryStore,
)
from minicode.models.scripted import (
    ScriptedModel,
)
from minicode.tools.scripted import (
    ScriptedToolRuntime,
)


@pytest.mark.asyncio
async def test_memory_learned_in_one_run_is_used_in_later_run() -> None:
    scope = MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key="MyCode",
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "pyproject.toml",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output=('requires-python = ">=3.12"'),
    )
    first_model = ScriptedModel(
        responses=(
            ModelResponse(
                content="",
                tool_calls=(tool_call,),
            ),
            ModelResponse(
                content=("This repository requires Python 3.12."),
            ),
        ),
    )
    first_loop = QueryLoop(
        model=first_model,
        tool_runtime=(
            ScriptedToolRuntime(
                results=(tool_result,),
            )
        ),
        max_turns=2,
    )
    first_user_message = Message(
        role=MessageRole.USER,
        content=("Inspect the required Python version."),
    )

    first_result = await first_loop.run((first_user_message,))

    proposal = MemoryProposal(
        content=("This repository requires Python 3.12."),
        scope=scope,
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.TOOL_RESULT),
                reference=("run_001:call_001"),
                excerpt=tool_result.output,
            ),
        ),
    )
    extractor = ScriptedMemoryExtractor(
        candidates=(proposal,),
    )
    store = InMemoryMemoryStore()
    learner = MemoryLearner(
        extractor=extractor,
        evidence_verifier=(RunEvidenceVerifier()),
        service=MemoryService(
            store=store,
            clock=lambda: 100.0,
            memory_id_factory=(lambda: "memory_001"),
        ),
    )
    extraction_request = MemoryExtractionRequest(
        run_id="run_001",
        scope=scope,
        message_history=(first_result.message_history),
        response=(first_result.response),
    )

    learning_result = await learner.learn(extraction_request)

    assert learning_result.writes[0].outcome is (MemoryWriteOutcome.SAVED)

    second_model = ScriptedModel(
        responses=(
            ModelResponse(
                content=("The repository requires Python 3.12."),
            ),
        ),
    )
    second_loop = QueryLoop(
        model=second_model,
        memory_context_provider=(
            MemoryContextBuilder(
                retriever=(
                    KeywordMemoryRetriever(
                        store=store,
                        clock=(lambda: 101.0),
                    )
                ),
                scopes=(scope,),
            )
        ),
    )
    second_user_message = Message(
        role=MessageRole.USER,
        content=("Which Python version does this repository require?"),
    )

    second_result = await second_loop.run((second_user_message,))

    assert second_model.requests[0].conversation == (second_user_message,)

    assert len(second_model.requests[0].instructions) == 1

    memory_instruction = second_model.requests[0].instructions[0]

    assert "This repository requires Python 3.12." in memory_instruction
    assert "tool_result: run_001:call_001" in memory_instruction
    assert first_user_message not in (second_model.requests[0].conversation)
    assert second_result.response.content == ("The repository requires Python 3.12.")
