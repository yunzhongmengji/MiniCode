import pytest

from minicode.core.checkpoints import InMemoryCheckpointStore, RunCheckpoint
from minicode.core.context_retrieval import (
    PendingToolResultError,
    RunHistoryMismatchError,
    RunHistoryNotFoundError,
    RunToolResultSource,
    UnknownToolCallError,
    get_tool_result,
)
from minicode.core.tool_calls import ToolCall, ToolResult


def test_get_tool_result_returns_the_original_historical_result() -> None:
    original_result = ToolResult(
        call_id="call_read_before_edit",
        output="timeout = 3",
    )
    current_result = ToolResult(
        call_id="call_read_after_edit",
        output="timeout = 5",
    )
    conversation = (
        ToolCall(
            call_id="call_read_before_edit",
            name="read_file",
            arguments={"path": "config.py"},
        ),
        original_result,
        ToolCall(
            call_id="call_edit",
            name="edit_file",
            arguments={
                "path": "config.py",
                "old_text": "timeout = 3",
                "new_text": "timeout = 5",
            },
        ),
        ToolResult(
            call_id="call_edit",
            output="updated config.py",
        ),
        ToolCall(
            call_id="call_read_after_edit",
            name="read_file",
            arguments={"path": "config.py"},
        ),
        current_result,
    )

    retrieved = get_tool_result(
        conversation,
        "call_read_before_edit",
    )

    assert retrieved is original_result
    assert retrieved.output == "timeout = 3"
    assert conversation[-1] is current_result


def test_get_tool_result_rejects_a_pending_tool_call() -> None:
    conversation = (
        ToolCall(
            call_id="call_pending",
            name="read_file",
            arguments={"path": "README.md"},
        ),
    )

    with pytest.raises(
        PendingToolResultError,
        match="tool call has no result yet: call_pending",
    ):
        get_tool_result(conversation, "call_pending")


def test_get_tool_result_rejects_an_unknown_call_id() -> None:
    with pytest.raises(
        UnknownToolCallError,
        match="tool call not found: call_missing",
    ):
        get_tool_result((), "call_missing")


@pytest.mark.parametrize(
    ("call_id", "error_type", "message"),
    (
        (None, TypeError, "call_id must be a string"),
        ("  ", ValueError, "call_id must not be blank"),
    ),
)
def test_get_tool_result_validates_call_id(
    call_id: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        get_tool_result((), call_id)  # type: ignore[arg-type]


def test_run_source_reads_only_the_bound_run() -> None:
    store = InMemoryCheckpointStore()
    first_run_result = ToolResult(
        call_id="call_shared",
        output="result from run 001",
    )
    second_run_result = ToolResult(
        call_id="call_shared",
        output="result from run 002",
    )
    store.save(
        _checkpoint_with_result(
            run_id="run_001",
            result=first_run_result,
        )
    )
    store.save(
        _checkpoint_with_result(
            run_id="run_002",
            result=second_run_result,
        )
    )
    source = RunToolResultSource(
        store,
        run_id="run_001",
    )

    retrieved = source.get("call_shared")

    assert source.run_id == "run_001"
    assert retrieved is first_run_result


def test_run_source_reads_the_latest_checkpoint() -> None:
    store = InMemoryCheckpointStore()
    source = RunToolResultSource(
        store,
        run_id="run_001",
    )
    first_result = ToolResult(
        call_id="call_001",
        output="first result",
    )
    second_result = ToolResult(
        call_id="call_002",
        output="second result",
    )
    store.save(
        _checkpoint_with_result(
            run_id="run_001",
            result=first_result,
        )
    )
    store.save(
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                _tool_call_for(first_result),
                first_result,
                _tool_call_for(second_result),
                second_result,
            ),
            turns_used=2,
            tool_calls_used=2,
        )
    )

    assert source.get("call_002") is second_result


def test_run_source_rejects_a_run_without_a_checkpoint() -> None:
    source = RunToolResultSource(
        InMemoryCheckpointStore(),
        run_id="run_missing",
    )

    with pytest.raises(
        RunHistoryNotFoundError,
        match="no checkpoint found for run: run_missing",
    ):
        source.get("call_001")


def test_run_source_rejects_a_mismatched_checkpoint() -> None:
    class MismatchedCheckpointStore:
        def latest(self, run_id: str) -> RunCheckpoint | None:
            return RunCheckpoint(
                run_id="run_other",
                message_history=(),
                turns_used=0,
                tool_calls_used=0,
            )

        def save(self, checkpoint: RunCheckpoint) -> None:
            raise AssertionError("save must not be called")

    source = RunToolResultSource(
        MismatchedCheckpointStore(),
        run_id="run_expected",
    )

    with pytest.raises(
        RunHistoryMismatchError,
        match="checkpoint run_id does not match tool-result source run_id",
    ):
        source.get("call_001")


def _checkpoint_with_result(
    *,
    run_id: str,
    result: ToolResult,
) -> RunCheckpoint:
    return RunCheckpoint(
        run_id=run_id,
        message_history=(
            _tool_call_for(result),
            result,
        ),
        turns_used=1,
        tool_calls_used=1,
    )


def _tool_call_for(result: ToolResult) -> ToolCall:
    return ToolCall(
        call_id=result.call_id,
        name="read_file",
        arguments={"path": "README.md"},
    )
