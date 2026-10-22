"""Prove evaluation stopping rules at the actual model/tool boundary."""

import pytest

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse, ModelRunBudget, ModelUsage
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.replay import RunReplay
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.evaluation_result import summarize_trace
from minicode.models.scripted import ScriptedModel
from minicode.tools.scripted import ScriptedToolRuntime

_MESSAGES = (Message(role=MessageRole.USER, content="Repair the fixture."),)
_CALL = ToolCall(call_id="read", name="read_file", arguments={"path": "a.py"})
_BUDGET = ModelRunBudget(100, 20, 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_calls", ((), (_CALL,)))
async def test_missing_usage_stops_before_tools_or_second_model_call(
    tool_calls,
) -> None:
    model = ScriptedModel(
        responses=[
            ModelResponse(content="response", tool_calls=tool_calls),
            ModelResponse(content="must never be requested"),
        ]
    )
    runtime = ScriptedToolRuntime(results=[])
    ledger = InMemoryEventLedger(run_id="run_missing_usage")
    loop = QueryLoop(
        model,
        max_turns=3,
        tool_runtime=runtime,
        model_budget=_BUDGET,
        event_ledger=ledger,
    )

    result = await loop.run(_MESSAGES)

    assert result.stop_reason is StopReason.USAGE_MISSING
    assert len(model.calls) == 1
    assert runtime.calls == ()
    summary = summarize_trace(RunReplay(events=ledger.events))
    assert summary["usage_complete"] is False
    assert summary["stop_reason"] == "usage_missing"
    assert summary["model_budget"]["require_complete_usage"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("second_usage", [ModelUsage(40, 1), ModelUsage(1, 10)])
async def test_cumulative_input_or_output_threshold_stops_next_actions(
    second_usage,
) -> None:
    second_call = ToolCall(
        call_id="second", name="read_file", arguments={"path": "b.py"}
    )
    model = ScriptedModel(
        responses=[
            ModelResponse(content="", tool_calls=(_CALL,), usage=ModelUsage(60, 10)),
            ModelResponse(content="", tool_calls=(second_call,), usage=second_usage),
            ModelResponse(content="must never be requested", usage=ModelUsage(1, 1)),
        ]
    )
    runtime = ScriptedToolRuntime(results=[ToolResult(call_id="read", output="a")])
    ledger = InMemoryEventLedger(run_id="run_token_threshold")
    loop = QueryLoop(
        model,
        max_turns=3,
        tool_runtime=runtime,
        model_budget=_BUDGET,
        event_ledger=ledger,
    )

    result = await loop.run(_MESSAGES)

    assert result.stop_reason is StopReason.TOKEN_BUDGET
    assert len(model.calls) == 2
    assert runtime.calls == (_CALL,)
    finished = [e for e in ledger.events if e.kind is EventKind.MODEL_CALL_FINISHED]
    assert (
        finished[-1].payload["cumulative_input_tokens"]
        == 60 + second_usage.input_tokens
    )
    assert (
        finished[-1].payload["cumulative_output_tokens"]
        == 10 + second_usage.output_tokens
    )
    assert finished[-1].payload["budget_stop_reason"] == "token_budget"


@pytest.mark.asyncio
async def test_response_overshoot_is_recorded_and_stopped_not_reported_completed() -> (
    None
):
    model = ScriptedModel(
        responses=[ModelResponse(content="Done", usage=ModelUsage(120, 11))]
    )
    ledger = InMemoryEventLedger(run_id="run_overshoot")
    result = await QueryLoop(model, model_budget=_BUDGET, event_ledger=ledger).run(
        _MESSAGES
    )
    assert result.stop_reason is StopReason.TOKEN_BUDGET
    summary = summarize_trace(RunReplay(events=ledger.events))
    assert summary["input_tokens"] == 120
    assert summary["output_tokens"] == 11
    assert summary["usage_complete"] is True


@pytest.mark.asyncio
async def test_unbudgeted_run_still_accepts_response_without_usage() -> None:
    result = await QueryLoop(
        ScriptedModel(responses=[ModelResponse(content="Done")])
    ).run(_MESSAGES)
    assert result.stop_reason is StopReason.COMPLETED


@pytest.mark.asyncio
async def test_provider_response_above_single_output_limit_stops() -> None:
    model = ScriptedModel(
        responses=[ModelResponse(content="Done", usage=ModelUsage(1, 11))]
    )
    result = await QueryLoop(model, model_budget=_BUDGET).run(_MESSAGES)
    assert result.stop_reason is StopReason.TOKEN_BUDGET


@pytest.mark.asyncio
async def test_budgeted_fresh_runs_do_not_share_token_counters() -> None:
    model = ScriptedModel(
        responses=[ModelResponse(content="Done", usage=ModelUsage(60, 1))] * 2
    )
    loop = QueryLoop(model, model_budget=_BUDGET)
    assert (await loop.run(_MESSAGES)).stop_reason is StopReason.COMPLETED
    assert (await loop.run(_MESSAGES)).stop_reason is StopReason.COMPLETED


@pytest.mark.asyncio
async def test_budgeted_resume_rejects_before_pending_tool_execution() -> None:
    model = ScriptedModel(responses=[])
    runtime = ScriptedToolRuntime(results=[])
    checkpoint = RunCheckpoint(
        run_id="run_budget_resume",
        message_history=(*_MESSAGES, _CALL),
        turns_used=1,
        tool_calls_used=0,
    )
    with pytest.raises(ValueError, match="require a fresh run"):
        await QueryLoop(
            model, max_turns=3, tool_runtime=runtime, model_budget=_BUDGET
        ).resume(checkpoint)
    assert model.calls == ()
    assert runtime.calls == ()


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_budget_rejects_invalid_limits(value) -> None:
    with pytest.raises((TypeError, ValueError)):
        ModelRunBudget(value, 20, 10)


def test_response_limit_cannot_exceed_run_limit() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        ModelRunBudget(100, 20, 21)
