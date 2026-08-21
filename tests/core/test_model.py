import pytest

from minicode.core.model import ModelResponse
from minicode.core.tool_calls import ToolCall


def test_model_response_stores_text_without_tool_calls() -> None:
    response = ModelResponse(
        content="MiniCode uses a query loop.",
    )

    assert response.content == "MiniCode uses a query loop."
    assert response.tool_calls == ()


def test_model_response_stores_tool_calls() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )

    response = ModelResponse(
        content="",
        tool_calls=(tool_call,),
    )

    assert response.content == ""
    assert response.tool_calls == (tool_call,)


def test_model_response_copies_tool_calls_from_caller() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    original_tool_calls = [tool_call]

    response = ModelResponse(
        content="",
        tool_calls=original_tool_calls,
    )

    original_tool_calls.clear()

    assert response.tool_calls == (tool_call,)


def test_model_response_rejects_non_tool_call_item() -> None:
    with pytest.raises(
        TypeError,
        match="tool_calls must contain only ToolCall instances",
    ):
        ModelResponse(
            content="",
            tool_calls=({"name": "read_file"},),
        )


def test_model_response_rejects_mapping_as_tool_calls() -> None:
    with pytest.raises(
        TypeError,
        match="tool_calls must be a sequence",
    ):
        ModelResponse(
            content="",
            tool_calls={},
        )


def test_model_response_rejects_non_string_content() -> None:
    with pytest.raises(
        TypeError,
        match="content must be a string",
    ):
        ModelResponse(
            content=None,
        )


def test_model_response_rejects_blank_response_without_tool_calls() -> None:
    with pytest.raises(
        ValueError,
        match="response must contain content or tool calls",
    ):
        ModelResponse(
            content="   ",
        )
