import asyncio

import pytest

from minicode.core.checkpoints import (
    InMemoryCheckpointStore,
    RunCheckpoint,
)
from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.core.messages import Message, MessageRole
from minicode.core.model import (
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.memory.context import (
    MemoryContext,
)
from minicode.memory.records import (
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeKind,
)
from minicode.memory.retrieval import (
    RankedMemory,
)
from minicode.models.scripted import ScriptedModel
from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.context import (
    SkillContext,
    SkillContextBuilder,
)
from minicode.skills.loader import (
    LoadedSkill,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.skills.router import (
    KeywordSkillRouter,
)
from minicode.tools.schema import ToolArguments
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.tools.spec import ToolSpec


class ReadFileArguments(ToolArguments):
    path: str


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
    event_ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    checkpoint_store = InMemoryCheckpointStore()
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
        event_ledger=event_ledger,
        checkpoint_store=checkpoint_store,
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
    assert checkpoint_store.latest("run_001") == RunCheckpoint(
        run_id="run_001",
        message_history=second_history,
        turns_used=1,
        tool_calls_used=1,
    )
    checkpoint_events = tuple(
        event
        for event in event_ledger.events
        if event.kind is EventKind.CHECKPOINT_SAVED
    )

    assert checkpoint_events == (
        LedgerEvent(
            run_id="run_001",
            sequence=4,
            kind=EventKind.CHECKPOINT_SAVED,
            payload={
                "turns_used": 1,
                "tool_calls_used": 1,
                "message_history_items": 4,
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_checkpoints_completed_tool_before_later_failure() -> None:
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
    model = ScriptedModel(
        responses=[
            ModelResponse(
                content="",
                tool_calls=(
                    first_tool_call,
                    second_tool_call,
                ),
            ),
        ],
    )
    tool_runtime = ScriptedToolRuntime(
        results=[
            first_tool_result,
        ],
    )
    event_ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    checkpoint_store = InMemoryCheckpointStore()
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
        event_ledger=event_ledger,
        checkpoint_store=checkpoint_store,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read both files.",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=("scripted tool runtime has no results remaining"),
    ):
        await loop.run(initial_history)

    assert checkpoint_store.latest("run_001") == RunCheckpoint(
        run_id="run_001",
        message_history=(
            *initial_history,
            first_tool_call,
            second_tool_call,
            first_tool_result,
        ),
        turns_used=1,
        tool_calls_used=1,
    )


@pytest.mark.asyncio
async def test_query_loop_resumes_only_pending_tool_calls() -> None:
    initial_message = Message(
        role=MessageRole.USER,
        content="Read both files.",
    )
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
    second_tool_result = ToolResult(
        call_id="call_002",
        output="Roadmap contents.",
    )

    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(
            initial_message,
            first_tool_call,
            second_tool_call,
            first_tool_result,
        ),
        turns_used=1,
        tool_calls_used=1,
    )

    final_response = ModelResponse(
        content="Both files have been read.",
    )
    model = ScriptedModel(
        responses=[
            final_response,
        ],
    )
    tool_runtime = ScriptedToolRuntime(
        results=[
            second_tool_result,
        ],
    )
    event_ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    checkpoint_store = InMemoryCheckpointStore()
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
        max_tool_calls=2,
        event_ledger=event_ledger,
        checkpoint_store=checkpoint_store,
    )

    result = await loop.resume(checkpoint)

    resumed_history = (
        *checkpoint.message_history,
        second_tool_result,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.response == final_response
    assert result.message_history == resumed_history
    assert result.turns_used == 2

    assert tool_runtime.calls == (second_tool_call,)
    assert model.calls == (resumed_history,)

    assert checkpoint_store.latest("run_001") == RunCheckpoint(
        run_id="run_001",
        message_history=resumed_history,
        turns_used=1,
        tool_calls_used=2,
    )
    assert tuple(event.kind for event in event_ledger.events) == (
        EventKind.RUN_RESUMED,
        EventKind.CHECKPOINT_SAVED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.RUN_FINISHED,
    )

    assert event_ledger.events[0] == LedgerEvent(
        run_id="run_001",
        sequence=1,
        kind=EventKind.RUN_RESUMED,
        payload={
            "message_history_items": 4,
            "turns_used": 1,
            "tool_calls_used": 1,
            "pending_tool_call_count": 1,
        },
    )

    assert event_ledger.events[-1] == LedgerEvent(
        run_id="run_001",
        sequence=5,
        kind=EventKind.RUN_FINISHED,
        payload={
            "outcome": "succeeded",
            "stop_reason": "completed",
            "turns_used": 2,
        },
    )


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


@pytest.mark.asyncio
async def test_query_loop_provides_tool_specs_to_model() -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    tool_spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file.",
        arguments_type=ReadFileArguments,
    )
    loop = QueryLoop(
        model=model,
        tool_specs=(tool_spec,),
    )
    conversation = (
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
    )

    await loop.run(conversation)

    assert model.requests[0].conversation == conversation
    assert model.requests[0].tool_specs == (tool_spec,)


@pytest.mark.parametrize(
    "tool_specs",
    [
        {},
        "",
        b"",
    ],
)
def test_query_loop_rejects_invalid_tool_specs_container(
    tool_specs: object,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        TypeError,
        match="tool_specs must be a sequence",
    ):
        QueryLoop(
            model=model,
            tool_specs=tool_specs,
        )


def test_query_loop_rejects_non_tool_spec_item() -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        TypeError,
        match="tool_specs must contain only ToolSpec instances",
    ):
        QueryLoop(
            model=model,
            tool_specs=["read_file"],
        )


@pytest.mark.asyncio
async def test_query_loop_snapshots_tool_specs() -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=[response],
    )
    tool_spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file.",
        arguments_type=ReadFileArguments,
    )
    original_tool_specs = [tool_spec]

    loop = QueryLoop(
        model=model,
        tool_specs=original_tool_specs,
    )
    original_tool_specs.clear()

    conversation = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    await loop.run(conversation)

    assert model.requests[0].tool_specs == (tool_spec,)


@pytest.mark.asyncio
async def test_query_loop_enforces_total_timeout() -> None:
    class NeverCompletingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request

            await asyncio.Event().wait()

            raise AssertionError("unreachable")

    loop = QueryLoop(
        model=NeverCompletingModel(),
        total_timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError):
        await loop.run(())


@pytest.mark.parametrize(
    "total_timeout_seconds",
    [
        True,
        "1.0",
        {},
        [],
    ],
)
def test_query_loop_rejects_non_numeric_total_timeout(
    total_timeout_seconds: object,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        TypeError,
        match=("total_timeout_seconds must be a number or None"),
    ):
        QueryLoop(
            model=model,
            total_timeout_seconds=total_timeout_seconds,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "total_timeout_seconds",
    [
        0,
        -1,
        float("inf"),
        float("-inf"),
        float("nan"),
    ],
)
def test_query_loop_rejects_invalid_total_timeout(
    total_timeout_seconds: float,
) -> None:
    model = ScriptedModel(
        responses=[],
    )

    with pytest.raises(
        ValueError,
        match=("total_timeout_seconds must be finite and greater than zero"),
    ):
        QueryLoop(
            model=model,
            total_timeout_seconds=total_timeout_seconds,
        )


@pytest.mark.asyncio
async def test_query_loop_propagates_external_cancellation() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    model_started = asyncio.Event()
    model_cleaned_up = asyncio.Event()

    class WaitingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request
            model_started.set()

            try:
                await asyncio.Event().wait()
            finally:
                model_cleaned_up.set()

            raise AssertionError("unreachable")

    loop = QueryLoop(
        model=WaitingModel(),
        total_timeout_seconds=10.0,
        event_ledger=ledger,
    )

    task = asyncio.create_task(loop.run(()))

    await model_started.wait()

    task.cancel()

    with pytest.raises(
        asyncio.CancelledError,
    ):
        await task

    assert model_cleaned_up.is_set()
    assert ledger.events[-2:] == (
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.MODEL_CALL_FINISHED,
            payload={
                "turn": 1,
                "outcome": "cancelled",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=4,
            kind=EventKind.RUN_FINISHED,
            payload={
                "outcome": "cancelled",
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_total_timeout_covers_tool_execution() -> None:
    tool_started = asyncio.Event()

    class NeverCompletingToolRuntime:
        async def execute(
            self,
            tool_call: ToolCall,
        ) -> ToolResult:
            del tool_call
            tool_started.set()

            await asyncio.Event().wait()

            raise AssertionError("unreachable")

    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    model = ScriptedModel(
        responses=[
            ModelResponse(
                content="I will read the file.",
                tool_calls=(tool_call,),
            ),
        ],
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=NeverCompletingToolRuntime(),
        max_turns=2,
        total_timeout_seconds=0.01,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md.",
        ),
    )

    with pytest.raises(TimeoutError):
        await loop.run(
            initial_history,
        )

    assert tool_started.is_set()
    assert model.calls == (initial_history,)


@pytest.mark.asyncio
async def test_query_loop_records_run_boundaries() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=[
            response,
        ],
    )
    loop = QueryLoop(
        model=model,
        max_turns=3,
        max_tool_calls=5,
        event_ledger=ledger,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Complete the task.",
        ),
    )

    result = await loop.run(initial_history)

    assert result.response is response
    assert ledger.events == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.RUN_STARTED,
            payload={
                "initial_history_items": 1,
                "max_turns": 3,
                "max_tool_calls": 5,
                "total_timeout_seconds": None,
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.MODEL_CALL_STARTED,
            payload={
                "turn": 1,
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.MODEL_CALL_FINISHED,
            payload={
                "turn": 1,
                "outcome": "succeeded",
                "tool_call_count": 0,
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=4,
            kind=EventKind.RUN_FINISHED,
            payload={
                "outcome": "succeeded",
                "stop_reason": "completed",
                "turns_used": 1,
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_records_model_usage() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    model = ScriptedModel(
        responses=[
            ModelResponse(
                content="Task completed.",
                usage=ModelUsage(
                    input_tokens=12,
                    output_tokens=5,
                ),
            ),
        ],
    )
    loop = QueryLoop(
        model=model,
        event_ledger=ledger,
    )

    await loop.run(())

    assert ledger.events[2] == LedgerEvent(
        run_id="run_001",
        sequence=3,
        kind=EventKind.MODEL_CALL_FINISHED,
        payload={
            "turn": 1,
            "outcome": "succeeded",
            "tool_call_count": 0,
            "input_tokens": 12,
            "output_tokens": 5,
        },
    )


@pytest.mark.asyncio
async def test_query_loop_records_timed_out_run() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )

    class NeverCompletingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request

            await asyncio.Event().wait()

            raise AssertionError("unreachable")

    loop = QueryLoop(
        model=NeverCompletingModel(),
        total_timeout_seconds=0.01,
        event_ledger=ledger,
    )

    with pytest.raises(
        TimeoutError,
    ):
        await loop.run(())

    assert ledger.events[-2:] == (
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.MODEL_CALL_FINISHED,
            payload={
                "turn": 1,
                "outcome": "cancelled",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=4,
            kind=EventKind.RUN_FINISHED,
            payload={
                "outcome": "timed_out",
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_records_failed_run() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )

    class FailingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request

            raise RuntimeError("simulated model failure")

    loop = QueryLoop(
        model=FailingModel(),
        event_ledger=ledger,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated model failure",
    ):
        await loop.run(())

    assert ledger.events[-2:] == (
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.MODEL_CALL_FINISHED,
            payload={
                "turn": 1,
                "outcome": "failed",
                "error_type": "RuntimeError",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=4,
            kind=EventKind.RUN_FINISHED,
            payload={
                "outcome": "failed",
                "error_type": "RuntimeError",
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_reuses_skill_context_without_changing_history() -> None:
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
    )
    skill_context = SkillContext(
        skills=(
            LoadedSkill(
                manifest=manifest,
                instructions=("Run the smallest failing test first."),
            ),
        ),
    )

    class RecordingSkillContextProvider:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def build(
            self,
            query: str,
        ) -> SkillContext:
            self.queries.append(query)

            return skill_context

    tool_call = ToolCall(
        call_id="call_001",
        name="run_tests",
        arguments={
            "path": "tests",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="1 passed",
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="",
                tool_calls=(tool_call,),
            ),
            ModelResponse(
                content="Tests now pass.",
            ),
        ),
    )
    tool_runtime = ScriptedToolRuntime(
        results=(tool_result,),
    )
    provider = RecordingSkillContextProvider()
    loop = QueryLoop(
        model=model,
        tool_runtime=tool_runtime,
        max_turns=2,
        skill_context_provider=provider,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Explain the repository.",
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="What should I do next?",
        ),
        Message(
            role=MessageRole.USER,
            content=("Fix the failing pytest test."),
        ),
    )

    result = await loop.run(initial_history)

    expected_history = (
        *initial_history,
        tool_call,
        tool_result,
    )
    rendered = skill_context.render()

    assert provider.queries == [
        "Fix the failing pytest test.",
    ]
    assert tuple(request.instructions for request in model.requests) == (
        (rendered,),
        (rendered,),
    )
    assert model.calls == (
        initial_history,
        expected_history,
    )
    assert result.message_history == (expected_history)


@pytest.mark.asyncio
async def test_query_loop_records_skill_events_before_model_call() -> None:
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
        tags=("pytest",),
    )
    catalog = SkillCatalog()
    catalog.register(manifest)

    class StaticSkillLoader:
        async def load(
            self,
            selected_manifest: SkillManifest,
        ) -> LoadedSkill:
            return LoadedSkill(
                manifest=selected_manifest,
                instructions=("Run the smallest failing test first."),
            )

    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    builder = SkillContextBuilder(
        router=KeywordSkillRouter(
            catalog=catalog,
        ),
        loader=StaticSkillLoader(),
        event_ledger=ledger,
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="Task completed.",
            ),
        ),
    )
    loop = QueryLoop(
        model=model,
        event_ledger=ledger,
        skill_context_provider=builder,
    )

    await loop.run(
        (
            Message(
                role=MessageRole.USER,
                content=("Fix the pytest failure."),
            ),
        )
    )

    assert tuple(event.kind for event in ledger.events) == (
        EventKind.RUN_STARTED,
        EventKind.SKILL_SELECTION_FINISHED,
        EventKind.SKILL_LOAD_STARTED,
        EventKind.SKILL_LOAD_FINISHED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.RUN_FINISHED,
    )

    assert tuple(event.sequence for event in ledger.events) == (
        1,
        2,
        3,
        4,
        5,
        6,
        7,
    )

    assert model.requests[0].instructions == (
        (
            "# Loaded Skills\n"
            "\n"
            "## Skill: pytest-debugging\n"
            "\n"
            "Run the smallest failing "
            "test first."
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_combines_skill_and_memory_instructions() -> None:
    skill_context = SkillContext(
        skills=(
            LoadedSkill(
                manifest=SkillManifest(
                    name="pytest-debugging",
                    description=("Diagnose pytest failures."),
                    entrypoint="SKILL.md",
                ),
                instructions=("Run the smallest failing test first."),
            ),
        ),
    )
    scope = MemoryScope(
        kind=MemoryScopeKind.PROJECT,
        key="MyCode",
    )
    memory_record = MemoryRecord(
        memory_id="memory_001",
        content=("Run project tests with .venv/bin/pytest."),
        scope=scope,
        evidence=(
            MemoryEvidence(
                kind=(MemoryEvidenceKind.WORKSPACE_FILE),
                reference="README.md",
                excerpt=(".venv/bin/pytest"),
            ),
        ),
        created_at=100.0,
    )
    memory_context = MemoryContext(
        memories=(
            RankedMemory(
                record=memory_record,
                score=2,
            ),
        ),
    )

    class StaticSkillContextProvider:
        async def build(
            self,
            query: str,
        ) -> SkillContext:
            assert query == ("Fix the failing pytest test.")

            return skill_context

    class StaticMemoryContextProvider:
        async def build(
            self,
            query: str,
        ) -> MemoryContext:
            assert query == ("Fix the failing pytest test.")

            return memory_context

    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="Test fixed.",
            ),
        ),
    )
    loop = QueryLoop(
        model=model,
        skill_context_provider=(StaticSkillContextProvider()),
        memory_context_provider=(StaticMemoryContextProvider()),
    )
    user_message = Message(
        role=MessageRole.USER,
        content=("Fix the failing pytest test."),
    )

    result = await loop.run((user_message,))

    assert model.requests[0].instructions == (
        skill_context.render(),
        memory_context.render(),
    )
    assert model.requests[0].conversation == (user_message,)
    assert result.message_history == (user_message,)
