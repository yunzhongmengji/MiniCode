import pytest

from minicode.core.tool_calls import ToolCall


def test_tool_call_stores_identity_name_and_arguments() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )

    assert tool_call.call_id == "call_001"
    assert tool_call.name == "read_file"
    assert tool_call.arguments == {"path": "README.md"}


def test_tool_call_arguments_cannot_be_modified() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )

    with pytest.raises(TypeError):
        tool_call.arguments["path"] = "/home/user/.ssh/id_rsa"


def test_tool_call_copies_arguments_from_caller() -> None:
    original_arguments = {"path": "README.md"}

    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments=original_arguments,
    )

    original_arguments["path"] = "/home/user/.ssh/id_rsa"

    assert tool_call.arguments["path"] == "README.md"


def test_tool_call_copies_nested_arguments_from_caller() -> None:
    original_arguments = {
        "options": {
            "mode": "safe",
        }
    }

    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments=original_arguments,
    )

    original_arguments["options"]["mode"] = "dangerous"

    assert tool_call.arguments["options"]["mode"] == "safe"


def test_tool_call_nested_arguments_cannot_be_modified() -> None:
    original_arguments = {
        "options": {
            "mode": "safe",
        }
    }

    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments=original_arguments,
    )

    with pytest.raises(TypeError):
        tool_call.arguments["options"]["mode"] = "dangerous"


def test_tool_call_rejects_non_json_argument_value() -> None:
    with pytest.raises(
        TypeError,
        match="tool arguments must contain only JSON-compatible values",
    ):
        ToolCall(
            call_id="call_001",
            name="read_file",
            arguments={"callback": object()},
        )


def test_tool_call_rejects_non_string_argument_key() -> None:
    with pytest.raises(
        TypeError,
        match="tool argument keys must be strings",
    ):
        ToolCall(
            call_id="call_001",
            name="read_file",
            arguments={1: "README.md"},
        )


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_tool_call_rejects_non_finite_float(value: float) -> None:
    with pytest.raises(
        ValueError,
        match="tool argument numbers must be finite",
    ):
        ToolCall(
            call_id="call_001",
            name="calculator",
            arguments={"value": value},
        )


def test_tool_call_rejects_non_mapping_arguments() -> None:
    with pytest.raises(
        TypeError,
        match="tool arguments must be a mapping",
    ):
        ToolCall(
            call_id="call_001",
            name="read_file",
            arguments=["README.md"],
        )


def test_tool_call_rejects_blank_call_id() -> None:
    with pytest.raises(
        ValueError,
        match="call_id must not be blank",
    ):
        ToolCall(
            call_id="   ",
            name="read_file",
            arguments={},
        )


def test_tool_call_rejects_blank_name() -> None:
    with pytest.raises(
        ValueError,
        match="name must not be blank",
    ):
        ToolCall(
            call_id="call_001",
            name="   ",
            arguments={},
        )


def test_tool_call_rejects_non_string_call_id() -> None:
    with pytest.raises(
        TypeError,
        match="call_id must be a string",
    ):
        ToolCall(
            call_id=123,
            name="read_file",
            arguments={},
        )


def test_tool_call_rejects_non_string_name() -> None:
    with pytest.raises(
        TypeError,
        match="name must be a string",
    ):
        ToolCall(
            call_id="call_001",
            name=None,
            arguments={},
        )
