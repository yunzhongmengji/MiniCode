from minicode.core.context_retention import (
    ToolResultRetentionReason,
    plan_tool_result_retention,
)
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


def test_retention_can_protect_the_two_most_recent_result_batches() -> None:
    conversation = (
        ToolCall(
            call_id="call_search",
            name="search_text",
            arguments={"query": "DEFAULT_TIMEOUT"},
        ),
        ToolResult(call_id="call_search", output="older search evidence"),
        Message(role=MessageRole.ASSISTANT, content="Read the evidence file."),
        ToolCall(
            call_id="call_registry",
            name="read_file",
            arguments={"path": "client_registry.py"},
        ),
        ToolResult(call_id="call_registry", output="terminal evidence"),
        Message(role=MessageRole.ASSISTANT, content="Check the final diff."),
        ToolCall(call_id="call_diff", name="git_diff", arguments={}),
        ToolResult(call_id="call_diff", output="focused diff"),
    )

    one_batch = plan_tool_result_retention(conversation)
    two_batches = plan_tool_result_retention(
        conversation,
        protected_recent_batch_count=2,
    )

    assert one_batch.protected_call_ids == ("call_diff",)
    assert one_batch.eligible_call_ids == ("call_search", "call_registry")
    assert two_batches.protected_call_ids == ("call_registry", "call_diff")
    assert two_batches.eligible_call_ids == ("call_search",)


def test_retention_counts_parallel_tool_results_as_one_batch() -> None:
    conversation = (
        ToolCall(call_id="call_old", name="read_file", arguments={"path": "old"}),
        ToolResult(call_id="call_old", output="old"),
        Message(role=MessageRole.ASSISTANT, content="Read two files."),
        ToolCall(call_id="call_a", name="read_file", arguments={"path": "a"}),
        ToolCall(call_id="call_b", name="read_file", arguments={"path": "b"}),
        ToolResult(call_id="call_a", output="a"),
        ToolResult(call_id="call_b", output="b"),
    )

    plan = plan_tool_result_retention(
        conversation,
        protected_recent_batch_count=1,
    )

    assert plan.protected_call_ids == ("call_a", "call_b")
    assert plan.eligible_call_ids == ("call_old",)


def test_retention_does_not_search_behind_a_non_result_history_tail() -> None:
    result = ToolResult(call_id="call_old", output="already processed")
    conversation = (
        result,
        Message(role=MessageRole.ASSISTANT, content="The task is complete."),
    )

    plan = plan_tool_result_retention(
        conversation,
        protected_recent_batch_count=2,
    )

    assert plan.protected_call_ids == ()
    assert plan.eligible_call_ids == ("call_old",)


def test_retention_explains_every_protected_and_eligible_result() -> None:
    conversation = (
        ToolCall(call_id="call_eligible", name="read_file", arguments={}),
        ToolResult(call_id="call_eligible", output="small"),
        Message(role=MessageRole.ASSISTANT, content="Check the diff."),
        ToolCall(call_id="call_excluded", name="git_diff", arguments={}),
        ToolResult(call_id="call_excluded", output="small"),
        Message(role=MessageRole.ASSISTANT, content="Read a large result."),
        ToolCall(call_id="call_large", name="read_file", arguments={}),
        ToolResult(call_id="call_large", output="界" * 4),
        Message(role=MessageRole.ASSISTANT, content="Try another file."),
        ToolCall(call_id="call_error", name="read_file", arguments={}),
        ToolResult(call_id="call_error", output="missing", is_error=True),
        Message(role=MessageRole.ASSISTANT, content="Read the latest file."),
        ToolCall(call_id="call_recent", name="read_file", arguments={}),
        ToolResult(call_id="call_recent", output="latest"),
    )

    plan = plan_tool_result_retention(
        conversation,
        excluded_tool_names=frozenset({"git_diff"}),
        max_retrievable_output_bytes=10,
    )

    assert tuple(decision.reason for decision in plan.decisions) == (
        ToolResultRetentionReason.ELIGIBLE,
        ToolResultRetentionReason.PROTECTED_EXCLUDED_TOOL,
        ToolResultRetentionReason.PROTECTED_NOT_RETRIEVABLE,
        ToolResultRetentionReason.PROTECTED_ERROR,
        ToolResultRetentionReason.PROTECTED_RECENT,
    )
    assert plan.protected_call_ids == (
        "call_excluded",
        "call_large",
        "call_error",
        "call_recent",
    )
    assert plan.eligible_call_ids == ("call_eligible",)
