import pytest

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import RunResult, StopReason
from minicode.core.tool_calls import ToolCall


@pytest.mark.parametrize(
    "turns_used",
    [
        0,
        -1,
    ],
)
def test_run_result_rejects_non_positive_turns(
    turns_used: int,
) -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    history = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    with pytest.raises(
        ValueError,
        match="turns_used must be greater than zero",
    ):
        RunResult(
            stop_reason=StopReason.COMPLETED,
            response=response,
            message_history=history,
            turns_used=turns_used,
        )


@pytest.mark.parametrize(
    "turns_used",
    [
        True,
        1.5,
        "1",
        None,
    ],
)
def test_run_result_rejects_non_integer_turns(
    turns_used: object,
) -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    history = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    with pytest.raises(
        TypeError,
        match="turns_used must be an integer",
    ):
        RunResult(
            stop_reason=StopReason.COMPLETED,
            response=response,
            message_history=history,
            turns_used=turns_used,
        )


def test_run_result_rejects_completed_response_with_tool_calls() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    response = ModelResponse(
        content="I need to read the file.",
        tool_calls=(tool_call,),
    )
    history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
    )

    with pytest.raises(
        ValueError,
        match="completed result must not contain tool calls",
    ):
        RunResult(
            stop_reason=StopReason.COMPLETED,
            response=response,
            message_history=history,
            turns_used=1,
        )


@pytest.mark.parametrize(
    "stop_reason",
    [
        StopReason.TOOL_CALLS_PENDING,
        StopReason.MAX_TURNS,
    ],
)
def test_run_result_requires_tool_calls_for_non_completed_stop(
    stop_reason: StopReason,
) -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    history = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    with pytest.raises(
        ValueError,
        match="non-completed result must contain tool calls",
    ):
        RunResult(
            stop_reason=stop_reason,
            response=response,
            message_history=history,
            turns_used=1,
        )
