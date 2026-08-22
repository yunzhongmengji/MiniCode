import pytest

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.scripted import ScriptedToolRuntime


@pytest.mark.asyncio
async def test_query_loop_completes_on_text_response() -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    loop = QueryLoop(
        model=model,
    )
    messages = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    result = await loop.run(messages)

    assert result.stop_reason is StopReason.COMPLETED
    assert result.response == response
    assert result.turns_used == 1
    assert model.calls == (messages,)


@pytest.mark.asyncio
async def test_query_loop_stops_for_pending_tool_calls() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    response = ModelResponse(
        content="I need to read the file.",
        tool_calls=(tool_call,),
    )
    model = ScriptedModel(
        responses=[response],
    )
    loop = QueryLoop(
        model=model,
    )
    messages = (
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
    )

    result = await loop.run(messages)

    assert result.stop_reason is StopReason.TOOL_CALLS_PENDING
    assert result.response == response
    assert result.turns_used == 1
    assert model.calls == (messages,)


@pytest.mark.asyncio
async def test_query_loop_snapshots_message_history() -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    loop = QueryLoop(
        model=model,
    )
    message = Message(
        role=MessageRole.USER,
        content="Complete the task.",
    )
    original_messages = [message]

    result = await loop.run(original_messages)
    original_messages.clear()

    assert result.message_history == (message,)


def test_query_loop_rejects_non_positive_turn_budget() -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        ValueError,
        match="max_turns must be greater than zero",
    ):
        QueryLoop(
            model=model,
            max_turns=0,
        )


@pytest.mark.parametrize(
    "max_turns",
    [
        True,
        1.5,
        "3",
        None,
    ],
)
def test_query_loop_rejects_non_integer_turn_budget(
    max_turns: object,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        TypeError,
        match="max_turns must be an integer",
    ):
        QueryLoop(
            model=model,
            max_turns=max_turns,
        )


@pytest.mark.asyncio
async def test_query_loop_executes_scripted_tool_and_continues() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    first_response = ModelResponse(
        content="I will read the file.",
        tool_calls=(tool_call,),
    )
    final_response = ModelResponse(
        content="README.md has been read.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            final_response,
        ]
    )
    tool_runtime = ScriptedToolRuntime(
        results=[tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
    )

    result = await loop.run(initial_history)

    second_history = initial_history + (
        Message(
            role=MessageRole.ASSISTANT,
            content="I will read the file.",
        ),
        tool_call,
        tool_result,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.response == final_response
    assert result.message_history == second_history
    assert result.turns_used == 2
    assert model.calls == (
        initial_history,
        second_history,
    )
    assert tool_runtime.calls == (tool_call,)


@pytest.mark.asyncio
async def test_query_loop_does_not_execute_tools_after_turn_budget() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="write_file",
        arguments={
            "path": "result.txt",
            "content": "changed",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="File written.",
    )
    response = ModelResponse(
        content="I will write the file.",
        tool_calls=(tool_call,),
    )
    model = ScriptedModel(
        responses=[response],
    )
    tool_runtime = ScriptedToolRuntime(
        results=[tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=1,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Write result.txt",
        ),
    )

    result = await loop.run(initial_history)

    assert result.stop_reason is StopReason.MAX_TURNS
    assert result.response == response
    assert result.message_history == initial_history
    assert result.turns_used == 1
    assert model.calls == (initial_history,)
    assert tool_runtime.calls == ()


@pytest.mark.asyncio
async def test_query_loop_returns_tool_error_to_model() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "missing.md"},
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="missing.md was not found.",
        is_error=True,
    )
    first_response = ModelResponse(
        content="",
        tool_calls=(tool_call,),
    )
    final_response = ModelResponse(
        content="I could not read missing.md because it does not exist.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            final_response,
        ]
    )
    tool_runtime = ScriptedToolRuntime(
        results=[tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read missing.md",
        ),
    )
    result = await loop.run(initial_history)

    second_history = initial_history + (
        tool_call,
        tool_result,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.response == final_response
    assert result.turns_used == 2
    assert result.message_history == second_history
    assert model.calls == (
        initial_history,
        second_history,
    )
    assert tool_runtime.calls == (tool_call,)


@pytest.mark.asyncio
async def test_query_loop_propagates_exhausted_scripted_model() -> None:
    model = ScriptedModel(
        responses=[],
    )
    loop = QueryLoop(
        model=model,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="scripted model has no responses remaining",
    ):
        await loop.run(initial_history)


@pytest.mark.asyncio
async def test_query_loop_stops_after_budget_across_multiple_turns() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    first_tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="write_file",
        arguments={
            "path": "result.txt",
            "content": "changed",
        },
    )
    first_response = ModelResponse(
        content="",
        tool_calls=(first_tool_call,),
    )
    second_response = ModelResponse(
        content="",
        tool_calls=(second_tool_call,),
    )
    model = ScriptedModel(
        responses=[
            first_response,
            second_response,
        ]
    )
    tool_runtime = ScriptedToolRuntime(
        results=[first_tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md and write result.txt",
        ),
    )
    result = await loop.run(initial_history)
    second_history = initial_history + (
        first_tool_call,
        first_tool_result,
    )

    assert result.stop_reason is StopReason.MAX_TURNS
    assert result.response == second_response
    assert result.turns_used == 2
    assert result.message_history == second_history

    assert model.calls == (
        initial_history,
        second_history,
    )

    assert tool_runtime.calls == (first_tool_call,)


@pytest.mark.asyncio
async def test_query_loop_executes_multiple_tool_calls_in_order() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={"path": "pyproject.toml"},
    )
    first_tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    second_tool_result = ToolResult(
        call_id="call_002",
        output="pyproject.toml contents.",
    )
    first_response = ModelResponse(
        content="",
        tool_calls=(first_tool_call, second_tool_call),
    )
    second_response = ModelResponse(
        content="Both files have been read.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            second_response,
        ]
    )
    tool_runtime = ScriptedToolRuntime(
        results=[first_tool_result, second_tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md and pyproject.toml",
        ),
    )
    result = await loop.run(initial_history)
    second_history = initial_history + (
        first_tool_call,
        second_tool_call,
        first_tool_result,
        second_tool_result,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.turns_used == 2
    assert result.message_history == second_history

    assert model.calls == (
        initial_history,
        second_history,
    )

    assert tool_runtime.calls == (
        first_tool_call,
        second_tool_call,
    )


@pytest.mark.asyncio
async def test_query_loop_stops_before_exceeding_tool_call_budget() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="write_file",
        arguments={
            "path": "result.txt",
            "content": "changed",
        },
    )
    first_tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    first_response = ModelResponse(
        content="",
        tool_calls=(first_tool_call,),
    )
    second_response = ModelResponse(
        content="",
        tool_calls=(second_tool_call,),
    )
    model = ScriptedModel(
        responses=[
            first_response,
            second_response,
        ]
    )
    tool_runtime = ScriptedToolRuntime(
        results=[first_tool_result],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=3,
        max_tool_calls=1,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md and write result.txt",
        ),
    )
    result = await loop.run(initial_history)
    second_history = initial_history + (
        first_tool_call,
        first_tool_result,
    )

    assert result.stop_reason is StopReason.MAX_TOOL_CALLS
    assert result.response == second_response
    assert result.turns_used == 2
    assert result.message_history == second_history

    assert model.calls == (
        initial_history,
        second_history,
    )

    assert tool_runtime.calls == (first_tool_call,)


@pytest.mark.parametrize(
    "max_tool_calls",
    [
        0,
        -1,
    ],
)
def test_query_loop_rejects_non_positive_tool_call_budget(
    max_tool_calls: int,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        ValueError,
        match="max_tool_calls must be greater than zero",
    ):
        QueryLoop(
            model=model,
            max_tool_calls=max_tool_calls,
        )


@pytest.mark.parametrize(
    "max_tool_calls",
    [
        True,
        1.5,
        "3",
        None,
    ],
)
def test_query_loop_rejects_non_integer_tool_call_budget(
    max_tool_calls: object,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        TypeError,
        match="max_tool_calls must be an integer",
    ):
        QueryLoop(
            model=model,
            max_tool_calls=max_tool_calls,
        )


@pytest.mark.asyncio
async def test_query_loop_does_not_partially_execute_tool_call_batch() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={"path": "pyproject.toml"},
    )
    response = ModelResponse(
        content="",
        tool_calls=(first_tool_call, second_tool_call),
    )
    model = ScriptedModel(
        responses=[response],
    )
    tool_runtime = ScriptedToolRuntime(
        results=[],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
        max_tool_calls=1,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md and pyproject.toml",
        ),
    )
    result = await loop.run(initial_history)

    assert result.stop_reason is StopReason.MAX_TOOL_CALLS
    assert result.response == response
    assert result.turns_used == 1
    assert result.message_history == initial_history
    assert model.calls == (initial_history,)
    assert tool_runtime.calls == ()
