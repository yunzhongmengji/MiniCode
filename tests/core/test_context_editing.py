import pytest

from minicode.core.context_editing import (
    ContextPressureDecision,
    apply_context_editing_plan,
    assess_context_pressure,
    plan_context_editing,
)
from minicode.core.context_profile import profile_model_request
from minicode.core.context_retrieval import render_tool_result_reference
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.read_tool_result import ReadToolResultArguments
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class ReadFileArguments(ToolArguments):
    path: str


_READ_TOOL_RESULT_SPEC = ToolSpec(
    name="read_tool_result",
    description=(
        "Read the exact original output of an earlier tool call in this run."
    ),
    arguments_type=ReadToolResultArguments,
)


@pytest.mark.parametrize(
    ("request_bytes", "max_request_bytes", "error_type", "message"),
    (
        (True, 100, TypeError, "request_bytes must be an integer"),
        (100, True, TypeError, "max_request_bytes must be an integer"),
        (-1, 100, ValueError, "request_bytes must not be negative"),
        (100, 0, ValueError, "max_request_bytes must be greater than zero"),
    ),
)
def test_context_pressure_decision_rejects_invalid_sizes(
    request_bytes: object,
    max_request_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        ContextPressureDecision(
            request_bytes=request_bytes,  # type: ignore[arg-type]
            max_request_bytes=max_request_bytes,  # type: ignore[arg-type]
        )


def test_request_at_exact_budget_does_not_require_editing() -> None:
    request = ModelRequest(
        conversation=(
            Message(role=MessageRole.USER, content="Inspect the project."),
            ToolResult(call_id="call_001", output="evidence" * 20),
        ),
        tool_specs=(
            ToolSpec(
                name="read_file",
                description="Read one UTF-8 file.",
                arguments_type=ReadFileArguments,
            ),
        ),
    )
    request_bytes = profile_model_request(request).total_bytes

    decision = assess_context_pressure(
        request,
        max_request_bytes=request_bytes,
    )

    assert decision.editing_required is False
    assert decision.request_bytes == request_bytes
    assert decision.max_request_bytes == request_bytes
    assert decision.overflow_bytes == 0


def test_complete_request_one_byte_over_budget_requires_editing() -> None:
    request = ModelRequest(
        conversation=(ToolResult(call_id="call_001", output="x" * 500),),
        tool_specs=(
            ToolSpec(
                name="read_file",
                description="Read one UTF-8 file.",
                arguments_type=ReadFileArguments,
            ),
        ),
    )
    request_bytes = profile_model_request(request).total_bytes

    decision = assess_context_pressure(
        request,
        max_request_bytes=request_bytes - 1,
    )

    assert decision.editing_required is True
    assert decision.request_bytes == request_bytes
    assert decision.max_request_bytes == request_bytes - 1
    assert decision.overflow_bytes == 1


def test_tool_definitions_count_toward_the_pressure_decision() -> None:
    without_tool = ModelRequest(
        conversation=(Message(role=MessageRole.USER, content="Inspect it."),),
    )
    with_tool = ModelRequest(
        conversation=without_tool.conversation,
        tool_specs=(
            ToolSpec(
                name="read_file",
                description="Read one UTF-8 file.",
                arguments_type=ReadFileArguments,
            ),
        ),
    )
    budget = profile_model_request(without_tool).total_bytes

    baseline_decision = assess_context_pressure(
        without_tool,
        max_request_bytes=budget,
    )
    tool_decision = assess_context_pressure(
        with_tool,
        max_request_bytes=budget,
    )

    assert baseline_decision.editing_required is False
    assert tool_decision.editing_required is True
    assert tool_decision.overflow_bytes > 0
    assert with_tool.tool_specs[0].name == "read_file"


def test_editing_plan_leaves_a_request_within_budget_unchanged() -> None:
    request = ModelRequest(
        conversation=(Message(role=MessageRole.USER, content="Inspect it."),),
    )
    request_bytes = profile_model_request(request).total_bytes

    plan = plan_context_editing(
        request,
        max_request_bytes=request_bytes,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    assert plan.selected_call_ids == ()
    assert plan.planned_request_bytes == request_bytes
    assert plan.total_bytes_saved == 0
    assert plan.remaining_overflow_bytes == 0
    assert plan.budget_satisfied is True


def test_editing_plan_selects_oldest_candidate_and_counts_retrieval_spec() -> None:
    first_output = "a" * 2_000
    second_output = "b" * 2_000
    latest_output = "latest evidence"
    request = ModelRequest(
        conversation=(
            ToolCall(call_id="call_first", name="read_file", arguments={}),
            ToolResult(call_id="call_first", output=first_output),
            Message(role=MessageRole.ASSISTANT, content="Read another file."),
            ToolCall(call_id="call_second", name="read_file", arguments={}),
            ToolResult(call_id="call_second", output=second_output),
            Message(role=MessageRole.ASSISTANT, content="Check the latest file."),
            ToolCall(call_id="call_latest", name="read_file", arguments={}),
            ToolResult(call_id="call_latest", output=latest_output),
        ),
    )
    first_reference = ToolResult(
        call_id="call_first",
        output=render_tool_result_reference(
            call_id="call_first",
            original_output_bytes=len(first_output.encode("utf-8")),
        ),
    )
    expected_request = ModelRequest(
        conversation=(
            request.conversation[0],
            first_reference,
            *request.conversation[2:],
        ),
        tool_specs=(_READ_TOOL_RESULT_SPEC,),
    )
    budget = profile_model_request(expected_request).total_bytes

    plan = plan_context_editing(
        request,
        max_request_bytes=budget,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    assert plan.selected_call_ids == ("call_first",)
    assert plan.planned_request_bytes == budget
    assert plan.total_bytes_saved > 0
    assert plan.budget_satisfied is True
    assert request.conversation[1] == ToolResult(
        call_id="call_first",
        output=first_output,
    )


def test_editing_plan_reports_when_protected_content_cannot_fit_budget() -> None:
    request = ModelRequest(
        conversation=(
            ToolCall(call_id="call_latest", name="read_file", arguments={}),
            ToolResult(call_id="call_latest", output="x" * 1_000),
        ),
    )
    request_bytes = profile_model_request(request).total_bytes

    plan = plan_context_editing(
        request,
        max_request_bytes=request_bytes - 1,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    assert plan.selected_call_ids == ()
    assert plan.planned_request_bytes == request_bytes
    assert plan.remaining_overflow_bytes == 1
    assert plan.budget_satisfied is False


def test_editing_plan_rejects_savings_below_the_configured_minimum() -> None:
    request = ModelRequest(
        conversation=(
            ToolCall(call_id="call_old", name="read_file", arguments={}),
            ToolResult(call_id="call_old", output="x" * 1_000),
            Message(role=MessageRole.ASSISTANT, content="Read the latest file."),
            ToolCall(call_id="call_latest", name="read_file", arguments={}),
            ToolResult(call_id="call_latest", output="latest"),
        ),
    )
    request_bytes = profile_model_request(request).total_bytes

    plan = plan_context_editing(
        request,
        max_request_bytes=request_bytes - 1,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        minimum_net_savings_bytes=request_bytes,
    )

    assert plan.selected_call_ids == ()
    assert plan.planned_request_bytes == request_bytes
    assert plan.budget_satisfied is False


def test_editing_plan_cannot_be_applied_to_a_different_request() -> None:
    original_request = ModelRequest(
        conversation=(Message(role=MessageRole.USER, content="Inspect it."),),
    )
    original_bytes = profile_model_request(original_request).total_bytes
    plan = plan_context_editing(
        original_request,
        max_request_bytes=original_bytes,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )
    changed_request = ModelRequest(
        conversation=(
            Message(role=MessageRole.USER, content="Inspect a different project."),
        ),
    )

    with pytest.raises(
        ValueError,
        match="context editing plan does not match request bytes",
    ):
        apply_context_editing_plan(
            changed_request,
            plan,
            retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        )
