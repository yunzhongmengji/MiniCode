import asyncio

import pytest

from minicode.coding_agent import CodingAgent
from minicode.core.events import InMemoryEventLedger
from minicode.core.file_checkpoint_store import FileCheckpointStore
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.scripted import ScriptedToolRuntime


class InterruptOnSecondToolRuntime:
    """Complete one tool, then simulate interruption on the next."""

    def __init__(self, first_result: ToolResult) -> None:
        self._first_result = first_result
        self.calls: list[ToolCall] = []

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        self.calls.append(tool_call)

        if len(self.calls) == 1:
            return self._first_result

        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_coding_agent_recovers_interrupted_tool_batch_from_disk(
    tmp_path,
) -> None:
    first_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    second_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={"path": "docs/ROADMAP.md"},
    )
    first_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    second_result = ToolResult(
        call_id="call_002",
        output="Roadmap contents.",
    )
    checkpoint_root = tmp_path / "checkpoints"
    first_store = FileCheckpointStore(checkpoint_root)
    first_runtime = InterruptOnSecondToolRuntime(first_result)
    first_agent = CodingAgent(
        query_loop=QueryLoop(
            model=ScriptedModel(
                responses=[
                    ModelResponse(
                        content="",
                        tool_calls=(first_call, second_call),
                    )
                ]
            ),
            tool_runtime=first_runtime,
            max_turns=2,
            max_tool_calls=2,
            event_ledger=InMemoryEventLedger(run_id="run_001"),
            checkpoint_store=first_store,
        )
    )

    with pytest.raises(asyncio.CancelledError):
        await first_agent.run("Read both project files.")

    interrupted_checkpoint = FileCheckpointStore(checkpoint_root).latest("run_001")

    assert interrupted_checkpoint is not None
    assert tuple(first_runtime.calls) == (first_call, second_call)
    assert interrupted_checkpoint.pending_tool_calls == (second_call,)
    assert interrupted_checkpoint.tool_calls_used == 1
    assert interrupted_checkpoint.is_completed is False

    resumed_store = FileCheckpointStore(checkpoint_root)
    resumed_model = ScriptedModel(
        responses=[ModelResponse(content="Both files have been read.")]
    )
    resumed_runtime = ScriptedToolRuntime(results=[second_result])
    resumed_agent = CodingAgent(
        query_loop=QueryLoop(
            model=resumed_model,
            tool_runtime=resumed_runtime,
            max_turns=2,
            max_tool_calls=2,
            event_ledger=InMemoryEventLedger(run_id="run_001"),
            checkpoint_store=resumed_store,
        )
    )

    result = await resumed_agent.resume(interrupted_checkpoint)

    expected_history = (
        *interrupted_checkpoint.message_history,
        second_result,
    )
    assert resumed_runtime.calls == (second_call,)
    assert resumed_model.calls == (expected_history,)
    assert result.stop_reason is StopReason.COMPLETED
    assert result.turns_used == 2

    completed_checkpoint = FileCheckpointStore(checkpoint_root).latest("run_001")

    assert completed_checkpoint is not None
    assert completed_checkpoint.message_history == expected_history
    assert completed_checkpoint.tool_calls_used == 2
    assert completed_checkpoint.is_completed is True

    final_model = ScriptedModel(responses=[])
    final_runtime = ScriptedToolRuntime(results=[])
    final_ledger = InMemoryEventLedger(run_id="run_001")
    final_agent = CodingAgent(
        query_loop=QueryLoop(
            model=final_model,
            tool_runtime=final_runtime,
            max_turns=3,
            max_tool_calls=3,
            event_ledger=final_ledger,
        )
    )

    with pytest.raises(ValueError, match="cannot resume a completed run"):
        await final_agent.resume(completed_checkpoint)

    assert final_model.calls == ()
    assert final_runtime.calls == ()
    assert final_ledger.events == ()
