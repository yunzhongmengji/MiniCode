import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from minicode.coding_agent import (
    CodingAgent,
    build_coding_agent,
    build_default_coding_policy,
)
from minicode.core.artifacts import InMemoryArtifactStore
from minicode.core.checkpoints import (
    InMemoryCheckpointStore,
    RunCheckpoint,
)
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.models.scripted import ScriptedModel
from minicode.tools.process import AsyncioProcessRunner
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.workspace import Workspace


def _budgeted_context_configuration() -> BudgetedContextProjectionConfiguration:
    return BudgetedContextProjectionConfiguration(
        max_request_bytes=1_000,
        protected_recent_batch_count=1,
        minimum_net_savings_bytes=1,
        excluded_tool_names=(),
        max_retrievable_output_bytes=50_000,
    )


def test_default_coding_policy_separates_observation_and_side_effects() -> None:
    policy = build_default_coding_policy()
    outcomes = {
        tool_name: policy.evaluate(
            ToolCall(
                call_id=f"call_{tool_name}",
                name=tool_name,
                arguments={},
            )
        ).outcome
        for tool_name in (
            "list_files",
            "read_file",
            "search_text",
            "git_diff",
            "read_tool_result",
            "create_file",
            "edit_file",
            "run_tests",
            "unknown_tool",
        )
    }

    assert outcomes == {
        "list_files": PolicyOutcome.ALLOW,
        "read_file": PolicyOutcome.ALLOW,
        "search_text": PolicyOutcome.ALLOW,
        "git_diff": PolicyOutcome.ALLOW,
        "read_tool_result": PolicyOutcome.ALLOW,
        "create_file": PolicyOutcome.ASK,
        "edit_file": PolicyOutcome.ASK,
        "run_tests": PolicyOutcome.ASK,
        "unknown_tool": PolicyOutcome.DENY,
    }


@pytest.mark.asyncio
async def test_coding_agent_starts_query_loop_from_task() -> None:
    response = ModelResponse(
        content="Task completed.",
    )
    model = ScriptedModel(
        responses=(response,),
    )
    agent = CodingAgent(
        query_loop=QueryLoop(
            model=model,
        ),
    )

    result = await agent.run("Inspect the failing test.")

    expected_message = Message(
        role=MessageRole.USER,
        content="Inspect the failing test.",
    )
    assert model.calls == ((expected_message,),)
    assert result.stop_reason is StopReason.COMPLETED
    assert result.response is response


@pytest.mark.asyncio
async def test_coding_agent_resumes_only_pending_tool_calls() -> None:
    first_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    pending_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={"path": "docs/ROADMAP.md"},
    )
    first_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    pending_result = ToolResult(
        call_id="call_002",
        output="Roadmap contents.",
    )
    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(
            Message(
                role=MessageRole.USER,
                content="Read both files.",
            ),
            first_call,
            pending_call,
            first_result,
        ),
        turns_used=1,
        tool_calls_used=1,
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="Both files have been read.",
            ),
        ),
    )
    tool_runtime = ScriptedToolRuntime(
        results=(pending_result,),
    )
    agent = CodingAgent(
        query_loop=QueryLoop(
            model=model,
            tool_runtime=tool_runtime,
            max_turns=2,
            max_tool_calls=2,
            event_ledger=InMemoryEventLedger(
                run_id="run_001",
            ),
        ),
    )

    result = await agent.resume(checkpoint)

    resumed_history = (
        *checkpoint.message_history,
        pending_result,
    )
    assert tool_runtime.calls == (pending_call,)
    assert model.calls == (resumed_history,)
    assert result.message_history == resumed_history
    assert result.turns_used == 2
    assert result.stop_reason is StopReason.COMPLETED


@pytest.mark.asyncio
async def test_build_coding_agent_exposes_and_executes_default_tools(
    tmp_path: Path,
) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "MiniCode is a coding agent.\n",
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
        responses=(
            ModelResponse(
                content="",
                tool_calls=(tool_call,),
            ),
            ModelResponse(
                content="README.md describes MiniCode.",
            ),
        ),
    )
    event_ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    artifact_store = InMemoryArtifactStore()
    checkpoint_store = InMemoryCheckpointStore()
    agent = build_coding_agent(
        model=model,
        workspace=Workspace(tmp_path),
        policy=ConfiguredToolPolicy(
            decisions={
                "read_file": PolicyDecision(
                    outcome=PolicyOutcome.ALLOW,
                    reason="workspace reads are allowed",
                ),
            },
        ),
        process_runner=AsyncioProcessRunner(),
        event_ledger=event_ledger,
        artifact_store=artifact_store,
        checkpoint_store=checkpoint_store,
    )

    result = await agent.run("Inspect README.md.")

    assert tuple(spec.name for spec in model.requests[0].tool_specs) == (
        "list_files",
        "read_file",
        "search_text",
        "git_diff",
        "create_file",
        "edit_file",
        "run_tests",
    )
    instructions = model.requests[0].instructions

    assert len(instructions) == 1
    assert "Inspect relevant files before editing" in instructions[0]
    assert "Use git_diff to review non-trivial or multi-file changes" in instructions[0]
    assert "Run relevant tests after changing code" in instructions[0]
    assert model.requests[1].instructions == instructions
    assert model.requests[1].conversation == (
        Message(
            role=MessageRole.USER,
            content="Inspect README.md.",
        ),
        tool_call,
        ToolResult(
            call_id="call_001",
            output=('File "README.md":\nMiniCode is a coding agent.\n'),
        ),
    )
    assert result.stop_reason is StopReason.COMPLETED
    assert result.response.content == ("README.md describes MiniCode.")
    assert checkpoint_store.latest("run_001") == RunCheckpoint(
        run_id="run_001",
        message_history=(
            Message(
                role=MessageRole.USER,
                content="Inspect README.md.",
            ),
            tool_call,
            ToolResult(
                call_id="call_001",
                output=('File "README.md":\nMiniCode is a coding agent.\n'),
            ),
        ),
        turns_used=2,
        tool_calls_used=1,
        is_completed=True,
    )
    event_kinds = tuple(event.kind for event in event_ledger.events)
    assert event_kinds.index(EventKind.MODEL_CALL_FINISHED) < event_kinds.index(
        EventKind.TOOL_POLICY_DECIDED
    )
    assert event_kinds.index(EventKind.TOOL_EXECUTION_FINISHED) < event_kinds.index(
        EventKind.MODEL_CALL_STARTED,
        2,
    )
    assert tuple(event.sequence for event in event_ledger.events) == tuple(
        range(
            1,
            len(event_ledger.events) + 1,
        )
    )
    tool_finished_event = next(
        event
        for event in event_ledger.events
        if event.kind is EventKind.TOOL_EXECUTION_FINISHED
    )
    output_artifact = tool_finished_event.payload["output_artifact"]
    assert isinstance(output_artifact, Mapping)
    artifact_id = output_artifact["artifact_id"]
    assert isinstance(artifact_id, str)
    assert artifact_store.read_text(artifact_id) == (
        'File "README.md":\nMiniCode is a coding agent.\n'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("projection_mode", ("threshold", "budget"))
async def test_opt_in_tool_result_references_support_historical_readback(
    tmp_path: Path,
    projection_mode: str,
) -> None:
    old_content = "historical evidence\n" * 40
    (tmp_path / "old.txt").write_text(old_content, encoding="utf-8")
    (tmp_path / "latest.txt").write_text("latest evidence\n", encoding="utf-8")
    old_read_call = ToolCall(
        call_id="call_read_old",
        name="read_file",
        arguments={"path": "old.txt"},
    )
    latest_read_call = ToolCall(
        call_id="call_read_latest",
        name="read_file",
        arguments={"path": "latest.txt"},
    )
    historical_read_call = ToolCall(
        call_id="call_restore_old",
        name="read_tool_result",
        arguments={"call_id": "call_read_old"},
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(content="", tool_calls=(old_read_call,)),
            ModelResponse(content="", tool_calls=(latest_read_call,)),
            ModelResponse(content="", tool_calls=(historical_read_call,)),
            ModelResponse(content="Historical evidence recovered."),
        )
    )
    event_ledger = InMemoryEventLedger(run_id="run_context_001")
    checkpoint_store = InMemoryCheckpointStore()
    projection_options: dict[str, object]

    if projection_mode == "threshold":
        projection_options = {"max_inline_tool_result_bytes": 100}
    else:
        projection_options = {
            "budgeted_context_configuration": _budgeted_context_configuration()
        }

    agent = build_coding_agent(
        model=model,
        workspace=Workspace(tmp_path),
        process_runner=AsyncioProcessRunner(),
        event_ledger=event_ledger,
        checkpoint_store=checkpoint_store,
        max_turns=4,
        max_tool_calls=3,
        **projection_options,  # type: ignore[arg-type]
    )

    result = await agent.run("Compare the old and latest evidence.")

    full_old_output = f'File "old.txt":\n{old_content}'
    assert "read_tool_result" not in {
        spec.name for spec in model.requests[0].tool_specs
    }
    assert "read_tool_result" not in {
        spec.name for spec in model.requests[1].tool_specs
    }
    assert model.requests[1].conversation[-1] == ToolResult(
        call_id="call_read_old",
        output=full_old_output,
    )

    projected_old_result = model.requests[2].conversation[2]
    assert isinstance(projected_old_result, ToolResult)
    assert json.loads(projected_old_result.output) == {
        "call_id": "call_read_old",
        "kind": "historical_tool_result_reference",
        "original_output_bytes": len(full_old_output.encode("utf-8")),
        "retrieval_tool": "read_tool_result",
    }
    assert "read_tool_result" in {spec.name for spec in model.requests[2].tool_specs}
    assert model.requests[3].conversation[-1] == ToolResult(
        call_id="call_restore_old",
        output=full_old_output,
    )

    canonical_old_result = result.message_history[2]
    assert canonical_old_result == ToolResult(
        call_id="call_read_old",
        output=full_old_output,
    )
    assert result.message_history[-1] == ToolResult(
        call_id="call_restore_old",
        output=full_old_output,
    )
    checkpoint = checkpoint_store.latest("run_context_001")
    assert checkpoint is not None
    assert checkpoint.message_history == result.message_history
    assert checkpoint.is_completed is True
    model_started_events = tuple(
        event
        for event in event_ledger.events
        if event.kind is EventKind.MODEL_CALL_STARTED
    )
    third_projection = model_started_events[2].payload["context_projection"]
    assert isinstance(third_projection, Mapping)

    if projection_mode == "threshold":
        assert third_projection["strategy"] == "tool_result_reference"
        assert third_projection["max_inline_tool_result_bytes"] == 100
        assert third_projection["configuration_schema_version"] == 2
    else:
        assert third_projection["strategy"] == "budgeted_tool_result_reference"
        assert third_projection["configuration_schema_version"] == 3
        assert third_projection["max_request_bytes"] == 1_000
        assert third_projection["protected_recent_batch_count"] == 1
        assert third_projection["excluded_tool_names"] == ()
        assert third_projection["max_retrievable_output_bytes"] == 50_000

    assert third_projection["minimum_net_savings_bytes"] == 1
    assert third_projection["retrieval_tool_loading"] == "on_reference"
    assert third_projection["changed_tool_result_count"] == 1
    tool_result_bytes_saved = third_projection["tool_result_bytes_saved"]
    total_bytes_saved = third_projection["total_bytes_saved"]
    assert isinstance(tool_result_bytes_saved, int)
    assert isinstance(total_bytes_saved, int)
    assert tool_result_bytes_saved > 0
    assert total_bytes_saved > 0
    successful_readback_events = tuple(
        event
        for event in event_ledger.events
        if event.kind is EventKind.TOOL_EXECUTION_FINISHED
        and event.payload.get("tool_name") == "read_tool_result"
        and event.payload.get("outcome") == "succeeded"
    )
    assert len(successful_readback_events) == 1


def test_tool_result_references_require_retrievable_run_state(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="tool-result references require an event_ledger for run binding",
    ):
        build_coding_agent(
            model=ScriptedModel(responses=(ModelResponse(content="Done."),)),
            workspace=Workspace(tmp_path),
            process_runner=AsyncioProcessRunner(),
            budgeted_context_configuration=_budgeted_context_configuration(),
        )


def test_context_projection_modes_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="are mutually exclusive"):
        build_coding_agent(
            model=ScriptedModel(responses=(ModelResponse(content="Done."),)),
            workspace=Workspace(tmp_path),
            process_runner=AsyncioProcessRunner(),
            max_inline_tool_result_bytes=100,
            budgeted_context_configuration=_budgeted_context_configuration(),
        )


def test_tool_result_references_require_checkpoint_store(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="tool-result references require a checkpoint_store for retrieval",
    ):
        build_coding_agent(
            model=ScriptedModel(responses=(ModelResponse(content="Done."),)),
            workspace=Workspace(tmp_path),
            process_runner=AsyncioProcessRunner(),
            event_ledger=InMemoryEventLedger(run_id="run_context_001"),
            max_inline_tool_result_bytes=100,
        )


@pytest.mark.asyncio
async def test_coding_agent_repairs_file_and_runs_real_tests(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "calculator.py"
    source_path.write_text(
        ("def add(left: int, right: int) -> int:\n    return left - right\n"),
        encoding="utf-8",
    )
    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_calculator.py").write_text(
        (
            "from calculator import add\n"
            "\n"
            "\n"
            "def test_adds_two_numbers() -> None:\n"
            "    assert add(2, 3) == 5\n"
        ),
        encoding="utf-8",
    )

    read_call = ToolCall(
        call_id="call_read",
        name="read_file",
        arguments={
            "path": "calculator.py",
        },
    )
    edit_call = ToolCall(
        call_id="call_edit",
        name="edit_file",
        arguments={
            "path": "calculator.py",
            "old_text": "return left - right",
            "new_text": "return left + right",
        },
    )
    test_call = ToolCall(
        call_id="call_test",
        name="run_tests",
        arguments={
            "path": "tests/test_calculator.py",
        },
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="I will inspect the implementation.",
                tool_calls=(read_call,),
            ),
            ModelResponse(
                content="I found the incorrect operator.",
                tool_calls=(edit_call,),
            ),
            ModelResponse(
                content="I will verify the fix.",
                tool_calls=(test_call,),
            ),
            ModelResponse(
                content=(
                    "Fixed the addition operator and verified the calculator test."
                ),
            ),
        ),
    )
    allow = PolicyDecision(
        outcome=PolicyOutcome.ALLOW,
        reason="allowed by coding integration test",
    )
    agent = build_coding_agent(
        model=model,
        workspace=Workspace(tmp_path),
        policy=ConfiguredToolPolicy(
            decisions={
                "read_file": allow,
                "edit_file": allow,
                "run_tests": allow,
            },
        ),
        process_runner=AsyncioProcessRunner(),
    )

    result = await agent.run("Fix the failing calculator test.")

    assert source_path.read_text(
        encoding="utf-8",
    ) == ("def add(left: int, right: int) -> int:\n    return left + right\n")
    assert len(model.requests) == 4

    test_results = tuple(
        item
        for item in model.requests[-1].conversation
        if isinstance(item, ToolResult) and item.call_id == "call_test"
    )
    assert len(test_results) == 1
    assert test_results[0].is_error is False
    assert "1 passed" in test_results[0].output
    assert result.stop_reason is StopReason.COMPLETED
    assert result.turns_used == 4
    assert result.response.content == (
        "Fixed the addition operator and verified the calculator test."
    )
