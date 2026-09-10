from collections.abc import Mapping

import pytest

from minicode.coding_agent import (
    CodingAgent,
    build_coding_agent,
    build_default_coding_policy,
)
from minicode.core.artifacts import InMemoryArtifactStore
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
from minicode.workspace import Workspace


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
async def test_build_coding_agent_exposes_and_executes_default_tools(
    tmp_path,
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
    )

    result = await agent.run("Inspect README.md.")

    assert tuple(spec.name for spec in model.requests[0].tool_specs) == (
        "list_files",
        "read_file",
        "search_text",
        "create_file",
        "edit_file",
        "run_tests",
    )
    instructions = model.requests[0].instructions

    assert len(instructions) == 1
    assert "Inspect relevant files before editing" in instructions[0]
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
async def test_coding_agent_repairs_file_and_runs_real_tests(
    tmp_path,
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
