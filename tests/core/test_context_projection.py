import pytest

from minicode.core.checkpoints import InMemoryCheckpointStore
from minicode.core.context_projection import (
    IdentityModelContextProjector,
    ToolResultReferenceProjector,
)
from minicode.core.events import InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest, ModelResponse
from minicode.core.query_loop import QueryLoop
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.read_tool_result import ReadToolResultArguments
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.tools.spec import ToolSpec

_READ_TOOL_RESULT_SPEC = ToolSpec(
    name="read_tool_result",
    description=(
        "Read the exact original output of an earlier tool call in the current run. "
        "This does not execute the earlier tool again."
    ),
    arguments_type=ReadToolResultArguments,
)


def _reference_projector(
    *, max_inline_output_bytes: int
) -> ToolResultReferenceProjector:
    return ToolResultReferenceProjector(
        max_inline_output_bytes=max_inline_output_bytes,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )


@pytest.mark.asyncio
async def test_identity_projector_preserves_request() -> None:
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Inspect the project.",
            ),
        )
    )

    projected = await IdentityModelContextProjector().project(request)

    assert projected is request


@pytest.mark.asyncio
async def test_reference_projector_compacts_only_eligible_large_result() -> None:
    older_output = "旧内容" * 100
    latest_output = "最新内容" * 100
    older_result = ToolResult(call_id="call_old", output=older_output)
    latest_result = ToolResult(call_id="call_latest", output=latest_output)
    request = ModelRequest(
        conversation=(
            ToolCall(
                call_id="call_old",
                name="read_file",
                arguments={"path": "old.py"},
            ),
            older_result,
            Message(role=MessageRole.ASSISTANT, content="Now inspect latest.py."),
            ToolCall(
                call_id="call_latest",
                name="read_file",
                arguments={"path": "latest.py"},
            ),
            latest_result,
        ),
        instructions=("Keep changes focused.",),
    )

    projected = await _reference_projector(max_inline_output_bytes=100).project(request)

    assert projected is not request
    assert projected.conversation[1] == ToolResult(
        call_id="call_old",
        output=(
            '{"call_id":"call_old",'
            '"kind":"historical_tool_result_reference",'
            '"original_output_bytes":900,'
            '"retrieval_tool":"read_tool_result"}'
        ),
    )
    assert projected.conversation[-1] is latest_result
    assert projected.instructions == request.instructions
    assert projected.tool_specs == (_READ_TOOL_RESULT_SPEC,)
    assert request.conversation[1] is older_result


@pytest.mark.asyncio
async def test_reference_projector_keeps_eligible_small_result_inline() -> None:
    small_result = ToolResult(call_id="call_small", output="small")
    request = ModelRequest(
        conversation=(
            small_result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=5).project(request)

    assert projected is request
    assert projected.conversation[0] is small_result


@pytest.mark.asyncio
async def test_reference_projector_never_expands_a_short_result() -> None:
    short_result = ToolResult(call_id="call_short", output="x" * 20)
    request = ModelRequest(
        conversation=(
            short_result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request


@pytest.mark.asyncio
async def test_reference_projector_preserves_earlier_error_result() -> None:
    error_result = ToolResult(
        call_id="call_error",
        output="permission denied" * 100,
        is_error=True,
    )
    request = ModelRequest(
        conversation=(
            error_result,
            Message(role=MessageRole.ASSISTANT, content="Try another path."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request
    assert projected.conversation[0] is error_result


@pytest.mark.parametrize(
    ("max_inline_output_bytes", "error_type", "message"),
    (
        (True, TypeError, "max_inline_output_bytes must be an integer"),
        (-1, ValueError, "max_inline_output_bytes must not be negative"),
    ),
)
def test_reference_projector_validates_byte_limit(
    max_inline_output_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        ToolResultReferenceProjector(
            max_inline_output_bytes=max_inline_output_bytes,  # type: ignore[arg-type]
            retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        )


@pytest.mark.asyncio
async def test_reference_projector_skips_projection_without_positive_net_savings() -> (
    None
):
    result = ToolResult(call_id="call_old", output="x" * 300)
    request = ModelRequest(
        conversation=(
            result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request
    assert projected.conversation[0] is result
    assert projected.tool_specs == ()


@pytest.mark.asyncio
async def test_query_loop_projects_only_the_model_view() -> None:
    class ReplacingToolOutputProjector:
        async def project(self, request: ModelRequest) -> ModelRequest:
            projected_conversation = tuple(
                ToolResult(
                    call_id=item.call_id,
                    output="[earlier output omitted]",
                    is_error=item.is_error,
                )
                if isinstance(item, ToolResult)
                else item
                for item in request.conversation
            )
            return ModelRequest(
                conversation=projected_conversation,
                tool_specs=request.tool_specs,
                instructions=request.instructions,
            )

    full_tool_result = ToolResult(
        call_id="call_001",
        output="complete file contents",
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="I will inspect it.",
                tool_calls=(tool_call,),
            ),
            ModelResponse(content="Inspection complete."),
        )
    )
    checkpoint_store = InMemoryCheckpointStore()
    loop = QueryLoop(
        model=model,
        tool_runtime=ScriptedToolRuntime(results=(full_tool_result,)),
        max_turns=2,
        context_projector=ReplacingToolOutputProjector(),
        event_ledger=InMemoryEventLedger(run_id="run_001"),
        checkpoint_store=checkpoint_store,
    )

    result = await loop.run(
        (
            Message(
                role=MessageRole.USER,
                content="Inspect README.md",
            ),
        )
    )

    assert model.requests[1].conversation[-1] == ToolResult(
        call_id="call_001",
        output="[earlier output omitted]",
    )
    assert result.message_history[-1] is full_tool_result

    checkpoint = checkpoint_store.latest("run_001")
    assert checkpoint is not None
    assert checkpoint.message_history[-1] is full_tool_result
