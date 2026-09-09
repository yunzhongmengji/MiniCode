from collections.abc import Mapping

import pytest

from minicode.core.artifacts import (
    InMemoryArtifactStore,
)
from minicode.core.checkpoints import (
    InMemoryCheckpointStore,
)
from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import ModelResponse
from minicode.core.query_loop import (
    QueryLoop,
    StopReason,
)
from minicode.core.replay import RunReplay
from minicode.core.tool_calls import ToolCall
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.models.scripted import ScriptedModel
from minicode.tools.dispatcher import (
    ToolDispatcher,
)
from minicode.tools.read_file import ReadFileTool
from minicode.tools.registry import ToolRegistry
from minicode.workspace import Workspace


def test_run_replay_reconstructs_summary() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )

    ledger.record(
        EventKind.RUN_STARTED,
        {
            "initial_history_items": 1,
        },
    )
    ledger.record(
        EventKind.MODEL_CALL_STARTED,
        {
            "turn": 1,
        },
    )
    ledger.record(
        EventKind.MODEL_CALL_FINISHED,
        {
            "turn": 1,
            "outcome": "succeeded",
            "tool_call_count": 1,
        },
    )
    ledger.record(
        EventKind.TOOL_EXECUTION_STARTED,
        {
            "call_id": "call_001",
            "tool_name": "read_file",
        },
    )
    ledger.record(
        EventKind.TOOL_EXECUTION_FINISHED,
        {
            "call_id": "call_001",
            "tool_name": "read_file",
            "outcome": "succeeded",
        },
    )
    ledger.record(
        EventKind.CHECKPOINT_SAVED,
        {
            "turns_used": 1,
            "tool_calls_used": 1,
            "message_history_items": 4,
        },
    )
    ledger.record(
        EventKind.RUN_FINISHED,
        {
            "outcome": "succeeded",
            "stop_reason": "completed",
            "turns_used": 2,
        },
    )

    source_events = list(ledger.events)

    replay = RunReplay(events=source_events)

    source_events.clear()

    assert replay.run_id == "run_001"
    assert replay.is_finished is True
    assert replay.outcome == "succeeded"

    assert replay.model_call_count == 1
    assert replay.tool_execution_count == 1
    assert replay.checkpoint_count == 1

    assert len(replay.events) == 7


def test_run_replay_rejects_corrupted_event_stream() -> None:
    started_event = LedgerEvent(
        run_id="run_001",
        sequence=1,
        kind=EventKind.RUN_STARTED,
        payload={},
    )

    with pytest.raises(
        ValueError,
        match=("events must belong to one run"),
    ):
        RunReplay(
            events=(
                started_event,
                LedgerEvent(
                    run_id="run_002",
                    sequence=2,
                    kind=(EventKind.RUN_FINISHED),
                    payload={
                        "outcome": "succeeded",
                    },
                ),
            ),
        )

    with pytest.raises(
        ValueError,
        match=("event sequences must be contiguous and start at one"),
    ):
        RunReplay(
            events=(
                started_event,
                LedgerEvent(
                    run_id="run_001",
                    sequence=3,
                    kind=(EventKind.RUN_FINISHED),
                    payload={
                        "outcome": "succeeded",
                    },
                ),
            ),
        )

    with pytest.raises(
        ValueError,
        match=("replay must start with a run boundary event"),
    ):
        RunReplay(
            events=(
                LedgerEvent(
                    run_id="run_001",
                    sequence=1,
                    kind=(EventKind.MODEL_CALL_STARTED),
                    payload={
                        "turn": 1,
                    },
                ),
            ),
        )

    with pytest.raises(
        ValueError,
        match=("finished run event must contain a string outcome"),
    ):
        RunReplay(
            events=(
                started_event,
                LedgerEvent(
                    run_id="run_001",
                    sequence=2,
                    kind=(EventKind.RUN_FINISHED),
                    payload={
                        "outcome": 17,
                    },
                ),
            ),
        )


@pytest.mark.asyncio
async def test_run_replay_summarizes_complete_tool_run(
    tmp_path,
) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "MiniCode replay contents.",
        encoding="utf-8",
    )

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
                content="I will read README.md.",
                tool_calls=(tool_call,),
            ),
            ModelResponse(
                content="README.md has been read.",
            ),
        ],
    )

    registry = ToolRegistry()
    registry.register(
        ReadFileTool(
            workspace=Workspace(
                root=tmp_path,
            ),
        )
    )

    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    artifact_store = InMemoryArtifactStore()
    checkpoint_store = InMemoryCheckpointStore()

    dispatcher = ToolDispatcher(
        registry=registry,
        policy=ConfiguredToolPolicy(
            decisions={
                "read_file": PolicyDecision(
                    outcome=(PolicyOutcome.ALLOW),
                    reason=("read access allowed by test policy"),
                ),
            },
        ),
        event_ledger=ledger,
        artifact_store=artifact_store,
    )

    loop = QueryLoop(
        model=model,
        tool_runtime=dispatcher,
        max_turns=2,
        tool_specs=registry.specs,
        event_ledger=ledger,
        checkpoint_store=checkpoint_store,
    )

    result = await loop.run(
        (
            Message(
                role=MessageRole.USER,
                content="Read README.md.",
            ),
        )
    )

    replay = RunReplay(
        events=ledger.events,
    )

    assert result.stop_reason is (StopReason.COMPLETED)
    assert result.response.content == ("README.md has been read.")

    assert replay.run_id == "run_001"
    assert replay.is_finished is True
    assert replay.outcome == "succeeded"
    assert replay.model_call_count == 2
    assert replay.tool_execution_count == 1
    assert replay.checkpoint_count == 1

    checkpoint = checkpoint_store.latest("run_001")

    assert checkpoint is not None
    assert checkpoint.turns_used == 1
    assert checkpoint.tool_calls_used == 1
    assert checkpoint.pending_tool_calls == ()

    tool_finished_event = next(
        event
        for event in ledger.events
        if event.kind is EventKind.TOOL_EXECUTION_FINISHED
    )
    artifact_metadata = tool_finished_event.payload["output_artifact"]

    assert isinstance(
        artifact_metadata,
        Mapping,
    )

    artifact_id = artifact_metadata["artifact_id"]

    assert isinstance(
        artifact_id,
        str,
    )
    assert artifact_store.read_text(artifact_id) == "MiniCode replay contents."


def test_run_replay_reports_failed_tool_calls() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    ledger.record(
        EventKind.RUN_STARTED,
        {},
    )

    ledger.record(
        EventKind.TOOL_EXECUTION_STARTED,
        {
            "call_id": "call_001",
            "tool_name": "read_file",
        },
    )
    ledger.record(
        EventKind.TOOL_EXECUTION_FINISHED,
        {
            "call_id": "call_001",
            "tool_name": "read_file",
            "outcome": "succeeded",
        },
    )

    ledger.record(
        EventKind.TOOL_EXECUTION_STARTED,
        {
            "call_id": "call_002",
            "tool_name": "edit_file",
        },
    )
    ledger.record(
        EventKind.TOOL_EXECUTION_FINISHED,
        {
            "call_id": "call_002",
            "tool_name": "edit_file",
            "outcome": "failed",
            "error_type": ("ToolExecutionError"),
        },
    )

    ledger.record(
        EventKind.TOOL_EXECUTION_STARTED,
        {
            "call_id": "call_003",
            "tool_name": "run_tests",
        },
    )
    ledger.record(
        EventKind.TOOL_EXECUTION_FINISHED,
        {
            "call_id": "call_003",
            "tool_name": "run_tests",
            "outcome": "cancelled",
        },
    )

    ledger.record(
        EventKind.RUN_FINISHED,
        {
            "outcome": "failed",
            "error_type": "RuntimeError",
        },
    )

    replay = RunReplay(
        events=ledger.events,
    )

    assert replay.tool_execution_count == 3
    assert replay.failed_tool_call_ids == ("call_002",)
