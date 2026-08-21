import pytest

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.tool_calls import ToolCall
from minicode.models.scripted import ScriptedModel


@pytest.mark.asyncio
async def test_scripted_model_returns_responses_in_order() -> None:
    first_response = ModelResponse(
        content="First response.",
    )
    second_response = ModelResponse(
        content="Second response.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            second_response,
        ]
    )
    messages = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    assert await model.complete(messages) == first_response
    assert await model.complete(messages) == second_response


@pytest.mark.asyncio
async def test_scripted_model_records_received_messages() -> None:
    response = ModelResponse(
        content="Done.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    messages = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    await model.complete(messages)

    assert model.calls == (messages,)


@pytest.mark.asyncio
async def test_scripted_model_copies_messages_from_caller() -> None:
    response = ModelResponse(
        content="Done.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    message = Message(
        role=MessageRole.USER,
        content="Complete the task.",
    )
    original_messages = [message]

    await model.complete(original_messages)
    original_messages.clear()

    assert model.calls == ((message,),)


@pytest.mark.asyncio
async def test_scripted_model_reports_exhausted_responses() -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        RuntimeError,
        match="scripted model has no responses remaining",
    ):
        await model.complete(())


@pytest.mark.asyncio
async def test_scripted_model_copies_responses_from_caller() -> None:
    response = ModelResponse(
        content="Done.",
    )
    original_responses = [response]
    model = ScriptedModel(
        responses=original_responses,
    )
    original_responses.clear()

    assert await model.complete(()) == response


def test_scripted_model_rejects_non_model_response() -> None:
    with pytest.raises(
        TypeError,
        match="responses must contain only ModelResponse instances",
    ):
        ScriptedModel(
            responses=["not a response"],
        )


@pytest.mark.parametrize(
    "responses",
    [
        {},
        "",
        b"",
    ],
)
def test_scripted_model_rejects_invalid_response_container(
    responses: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="responses must be a sequence",
    ):
        ScriptedModel(
            responses=responses,
        )


@pytest.mark.asyncio
async def test_scripted_model_scripts_tool_call_then_final_answer() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    first_response = ModelResponse(
        content="",
        tool_calls=[tool_call],
    )
    second_response = ModelResponse(
        content="README.md has been read.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            second_response,
        ]
    )
    first_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
    )

    first_result = await model.complete(first_history)

    assert first_result.tool_calls == (tool_call,)

    second_history = first_history + (
        Message(
            role=MessageRole.ASSISTANT,
            content="Calling read_file",
        ),
        Message(
            role=MessageRole.TOOL,
            content="README contents.",
        ),
    )

    second_result = await model.complete(second_history)

    assert second_result.content == "README.md has been read."
    assert second_result.tool_calls == ()
    assert model.calls == (
        first_history,
        second_history,
    )
