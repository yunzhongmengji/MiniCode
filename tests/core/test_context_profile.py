import pytest

from minicode.core.context_profile import (
    profile_context_projection,
    profile_model_request,
)
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest, ModelResponse
from minicode.core.query_loop import QueryLoop
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.schema import ToolArguments
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.tools.spec import ToolSpec


class ReadFileArguments(ToolArguments):
    path: str


def test_context_profile_separates_model_request_components() -> None:
    request = ModelRequest(
        instructions=("Follow project instructions.",),
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Read README.md",
            ),
            ToolCall(
                call_id="call_001",
                name="read_file",
                arguments={"path": "README.md"},
            ),
            ToolResult(
                call_id="call_001",
                output="README contents.",
            ),
        ),
        tool_specs=(
            ToolSpec(
                name="read_file",
                description="Read a UTF-8 text file.",
                arguments_type=ReadFileArguments,
            ),
        ),
    )

    profile = profile_model_request(request)

    assert profile.instruction_bytes > 0
    assert profile.message_bytes > 0
    assert profile.tool_definition_bytes > 0
    assert profile.tool_call_bytes > 0
    assert profile.tool_result_bytes > 0
    assert profile.total_bytes == sum(
        (
            profile.instruction_bytes,
            profile.message_bytes,
            profile.tool_definition_bytes,
            profile.tool_call_bytes,
            profile.tool_result_bytes,
        )
    )


def test_larger_tool_output_only_grows_tool_result_category() -> None:
    short_request = ModelRequest(
        conversation=(
            ToolResult(
                call_id="call_001",
                output="short",
            ),
        ),
    )
    long_request = ModelRequest(
        conversation=(
            ToolResult(
                call_id="call_001",
                output="a much longer tool output",
            ),
        ),
    )

    short_profile = profile_model_request(short_request)
    long_profile = profile_model_request(long_request)

    assert long_profile.tool_result_bytes > short_profile.tool_result_bytes
    assert long_profile.instruction_bytes == short_profile.instruction_bytes
    assert long_profile.message_bytes == short_profile.message_bytes
    assert long_profile.tool_definition_bytes == short_profile.tool_definition_bytes
    assert long_profile.tool_call_bytes == short_profile.tool_call_bytes


def test_context_projection_profile_measures_changed_tool_result() -> None:
    full_result = ToolResult(
        call_id="call_001",
        output="full historical output" * 100,
    )
    reference_result = ToolResult(
        call_id="call_001",
        output='{"call_id":"call_001"}',
    )
    canonical_request = ModelRequest(conversation=(full_result,))
    projected_request = ModelRequest(conversation=(reference_result,))

    profile = profile_context_projection(
        canonical_request,
        projected_request,
    )

    assert profile.changed_tool_result_count == 1
    assert profile.tool_result_bytes_before > profile.tool_result_bytes_after
    assert profile.tool_result_bytes_saved == (
        profile.tool_result_bytes_before - profile.tool_result_bytes_after
    )
    assert profile.total_bytes_before > profile.total_bytes_after
    assert profile.total_bytes_saved == (
        profile.total_bytes_before - profile.total_bytes_after
    )


@pytest.mark.asyncio
async def test_query_loop_profiles_growth_after_a_tool_result() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="I will inspect the file.",
                tool_calls=(tool_call,),
            ),
            ModelResponse(content="Inspection complete."),
        )
    )
    ledger = InMemoryEventLedger(run_id="run_001")
    loop = QueryLoop(
        model=model,
        tool_runtime=ScriptedToolRuntime(
            results=(
                ToolResult(
                    call_id="call_001",
                    output="A" * 1_000,
                ),
            )
        ),
        max_turns=2,
        instructions=("Follow project instructions.",),
        tool_specs=(
            ToolSpec(
                name="read_file",
                description="Read a UTF-8 text file.",
                arguments_type=ReadFileArguments,
            ),
        ),
        event_ledger=ledger,
    )

    await loop.run(
        (
            Message(
                role=MessageRole.USER,
                content="Inspect README.md",
            ),
        )
    )

    first_profile = profile_model_request(model.requests[0])
    second_profile = profile_model_request(model.requests[1])
    model_started_events = tuple(
        event for event in ledger.events if event.kind is EventKind.MODEL_CALL_STARTED
    )

    assert model_started_events[0].payload["context_profile"] == (
        first_profile.to_payload()
    )
    assert model_started_events[1].payload["context_profile"] == (
        second_profile.to_payload()
    )
    assert second_profile.instruction_bytes == first_profile.instruction_bytes
    assert second_profile.tool_definition_bytes == (first_profile.tool_definition_bytes)
    assert first_profile.tool_call_bytes == 0
    assert first_profile.tool_result_bytes == 0
    assert second_profile.tool_call_bytes > 0
    assert second_profile.tool_result_bytes > 1_000
    assert second_profile.message_bytes > first_profile.message_bytes
