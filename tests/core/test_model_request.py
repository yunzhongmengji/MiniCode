import pytest

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class ReadFileArguments(ToolArguments):
    path: str


def test_model_request_snapshots_conversation_and_tool_specs() -> None:
    original_instructions = [
        "Run the smallest failing test first.",
    ]
    message = Message(
        role=MessageRole.USER,
        content="Read README.md",
    )
    tool_spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file.",
        arguments_type=ReadFileArguments,
    )

    original_conversation = [message]
    original_tool_specs = [tool_spec]

    request = ModelRequest(
        conversation=original_conversation,
        tool_specs=original_tool_specs,
        instructions=original_instructions,
    )

    original_conversation.clear()
    original_tool_specs.clear()
    original_instructions.clear()

    assert request.conversation == (message,)
    assert request.tool_specs == (tool_spec,)
    assert request.instructions == ("Run the smallest failing test first.",)


@pytest.mark.parametrize(
    "conversation",
    [
        {},
        "",
        b"",
    ],
)
def test_model_request_rejects_invalid_conversation_container(
    conversation: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="conversation must be a sequence",
    ):
        ModelRequest(
            conversation=conversation,
        )


def test_model_request_rejects_non_conversation_item() -> None:
    with pytest.raises(
        TypeError,
        match="conversation must contain only ConversationItem instances",
    ):
        ModelRequest(
            conversation=[123],
        )


@pytest.mark.parametrize(
    "tool_specs",
    [
        {},
        "",
        b"",
    ],
)
def test_model_request_rejects_invalid_tool_specs_container(
    tool_specs: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="tool_specs must be a sequence",
    ):
        ModelRequest(
            conversation=[],
            tool_specs=tool_specs,
        )


def test_model_request_rejects_non_tool_spec_item() -> None:
    with pytest.raises(
        TypeError,
        match="tool_specs must contain only ToolSpec instances",
    ):
        ModelRequest(
            conversation=[],
            tool_specs=["read_file"],
        )
