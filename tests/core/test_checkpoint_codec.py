import json

import pytest

from minicode.core.checkpoint_codec import (
    checkpoint_from_json,
    checkpoint_to_json,
)
from minicode.core.checkpoints import RunCheckpoint
from minicode.core.messages import Message, MessageRole
from minicode.core.tool_calls import ToolCall, ToolResult


def test_checkpoint_json_round_trip_preserves_resume_state() -> None:
    completed_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    pending_call = ToolCall(
        call_id="call_002",
        name="search_text",
        arguments={
            "query": "CheckpointStore",
            "path": "src",
        },
    )
    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(
            Message(
                role=MessageRole.USER,
                content="Inspect checkpoint handling.",
            ),
            completed_call,
            pending_call,
            ToolResult(
                call_id="call_001",
                output="README contents.",
            ),
        ),
        turns_used=1,
        tool_calls_used=1,
    )

    encoded = checkpoint_to_json(checkpoint)
    decoded = checkpoint_from_json(encoded)
    document = json.loads(encoded)

    assert decoded == checkpoint
    assert decoded.pending_tool_calls == (pending_call,)
    assert document["schema_version"] == 2
    assert document["is_completed"] is False
    assert tuple(item["type"] for item in document["message_history"]) == (
        "message",
        "tool_call",
        "tool_call",
        "tool_result",
    )


def test_checkpoint_json_reads_legacy_progress_without_completion_flag() -> None:
    decoded = checkpoint_from_json(
        """{
  "schema_version": 1,
  "run_id": "run_legacy",
  "message_history": [],
  "turns_used": 1,
  "tool_calls_used": 0
}"""
    )

    assert decoded.run_id == "run_legacy"
    assert decoded.is_completed is False


def test_checkpoint_json_requires_completion_flag_in_version_two() -> None:
    with pytest.raises(TypeError, match="is_completed must be a boolean"):
        checkpoint_from_json(
            """{
  "schema_version": 2,
  "run_id": "run_001",
  "message_history": [],
  "turns_used": 1,
  "tool_calls_used": 0
}"""
        )


def test_checkpoint_json_rejects_an_unknown_schema() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported checkpoint schema 3",
    ):
        checkpoint_from_json(
            """{
  "schema_version": 3
}"""
        )
