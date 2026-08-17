import pytest

from minicode.core.tool_calls import ToolResult


def test_tool_result_stores_success_output() -> None:
    result = ToolResult(
        call_id="call_001",
        output="README contents",
        is_error=False,
    )

    assert result.call_id == "call_001"
    assert result.output == "README contents"
    assert result.is_error is False


def test_tool_result_allows_empty_output() -> None:
    result = ToolResult(
        call_id="call_001",
        output="",
    )

    assert result.output == ""
    assert result.is_error is False


def test_tool_result_rejects_non_string_output() -> None:
    with pytest.raises(
        TypeError,
        match="output must be a string",
    ):
        ToolResult(
            call_id="call_001",
            output=123,
        )


def test_tool_result_stores_error_output() -> None:
    result = ToolResult(
        call_id="call_001",
        output="File not found: README.md",
        is_error=True,
    )

    assert result.output == "File not found: README.md"
    assert result.is_error is True


def test_tool_result_rejects_non_boolean_error_flag() -> None:
    with pytest.raises(
        TypeError,
        match="is_error must be a boolean",
    ):
        ToolResult(
            call_id="call_001",
            output="File not found: README.md",
            is_error=1,
        )
