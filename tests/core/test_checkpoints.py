import pytest

from minicode.core.checkpoints import (
    InMemoryCheckpointStore,
    RunCheckpoint,
)
from minicode.core.conversation import (
    ConversationItem,
)
from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)


def test_run_checkpoint_snapshots_resume_state() -> None:
    user_message = Message(
        role=MessageRole.USER,
        content="Read README.md.",
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="MiniCode",
    )
    history: list[ConversationItem] = [
        user_message,
        tool_call,
        tool_result,
    ]

    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=history,
        turns_used=1,
        tool_calls_used=1,
    )

    history.append(
        Message(
            role=MessageRole.USER,
            content="This must not alter the checkpoint.",
        )
    )

    assert checkpoint.run_id == "run_001"
    assert checkpoint.message_history == (
        user_message,
        tool_call,
        tool_result,
    )
    assert checkpoint.turns_used == 1
    assert checkpoint.tool_calls_used == 1


def test_in_memory_checkpoint_store_returns_latest() -> None:
    store = InMemoryCheckpointStore()
    first_checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(),
        turns_used=1,
        tool_calls_used=0,
    )
    second_checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(),
        turns_used=2,
        tool_calls_used=0,
    )

    store.save(first_checkpoint)
    store.save(second_checkpoint)

    assert store.latest("run_001") is second_checkpoint
    assert store.latest("missing_run") is None


def test_run_checkpoint_identifies_pending_tool_calls() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={
            "path": "docs/ROADMAP.md",
        },
    )
    first_tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(
            first_tool_call,
            second_tool_call,
            first_tool_result,
        ),
        turns_used=1,
        tool_calls_used=1,
    )

    assert checkpoint.pending_tool_calls == (second_tool_call,)


def test_run_checkpoint_rejects_invalid_tool_history() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )

    with pytest.raises(
        ValueError,
        match="completed checkpoint must not contain pending tool calls",
    ):
        RunCheckpoint(
            run_id="run_001",
            message_history=(tool_call,),
            turns_used=1,
            tool_calls_used=0,
            is_completed=True,
        )

    with pytest.raises(
        ValueError,
        match="tool call ids must be unique",
    ):
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                tool_call,
                tool_call,
            ),
            turns_used=1,
            tool_calls_used=0,
        )

    with pytest.raises(
        ValueError,
        match=("tool result must match a preceding tool call"),
    ):
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                ToolResult(
                    call_id="call_missing",
                    output="unexpected",
                ),
            ),
            turns_used=1,
            tool_calls_used=1,
        )

    with pytest.raises(
        ValueError,
        match=("each tool call must have at most one result"),
    ):
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                tool_call,
                tool_result,
                tool_result,
            ),
            turns_used=1,
            tool_calls_used=2,
        )

    with pytest.raises(
        ValueError,
        match=("tool_calls_used must equal completed tool calls"),
    ):
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                tool_call,
                tool_result,
            ),
            turns_used=1,
            tool_calls_used=0,
        )
