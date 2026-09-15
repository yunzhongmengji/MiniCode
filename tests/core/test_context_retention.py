from minicode.core.context_retention import plan_tool_result_retention
from minicode.core.messages import Message, MessageRole
from minicode.core.tool_calls import ToolCall, ToolResult


def test_retention_protects_the_complete_latest_tool_result_batch() -> None:
    conversation = (
        Message(
            role=MessageRole.USER,
            content="Inspect the project.",
        ),
        ToolCall(
            call_id="call_001",
            name="list_files",
            arguments={},
        ),
        ToolResult(
            call_id="call_001",
            output="calculator.py",
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="I will read both files.",
        ),
        ToolCall(
            call_id="call_002",
            name="read_file",
            arguments={"path": "calculator.py"},
        ),
        ToolCall(
            call_id="call_003",
            name="read_file",
            arguments={"path": "tests/test_calculator.py"},
        ),
        ToolResult(
            call_id="call_002",
            output="calculator contents",
        ),
        ToolResult(
            call_id="call_003",
            output="test contents",
        ),
    )

    plan = plan_tool_result_retention(conversation)

    assert plan.protected_call_ids == (
        "call_002",
        "call_003",
    )
    assert plan.eligible_call_ids == ("call_001",)


def test_retention_protects_earlier_error_results() -> None:
    conversation = (
        ToolCall(
            call_id="call_001",
            name="read_file",
            arguments={"path": "missing.py"},
        ),
        ToolResult(
            call_id="call_001",
            output="file does not exist",
            is_error=True,
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="I will inspect another file.",
        ),
        ToolCall(
            call_id="call_002",
            name="read_file",
            arguments={"path": "README.md"},
        ),
        ToolResult(
            call_id="call_002",
            output="README contents",
        ),
    )

    plan = plan_tool_result_retention(conversation)

    assert plan.protected_call_ids == (
        "call_001",
        "call_002",
    )
    assert plan.eligible_call_ids == ()
