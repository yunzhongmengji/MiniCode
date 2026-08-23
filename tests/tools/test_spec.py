from dataclasses import FrozenInstanceError

import pytest

from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class ReadFileArguments(ToolArguments):
    """Arguments accepted by the example read-file tool."""

    path: str


def test_tool_spec_describes_tool() -> None:
    spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file.",
        arguments_type=ReadFileArguments,
    )

    assert spec.name == "read_file"
    assert spec.description == "Read a UTF-8 text file."
    assert spec.arguments_type is ReadFileArguments


def test_tool_spec_rejects_non_tool_arguments_type() -> None:
    with pytest.raises(
        TypeError,
        match="arguments_type must be a ToolArguments subclass",
    ):
        ToolSpec(
            name="read_file",
            description="Read a UTF-8 text file.",
            arguments_type=dict,
        )


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "\t",
    ],
)
def test_tool_spec_rejects_blank_name(name: str) -> None:
    with pytest.raises(
        ValueError,
        match="tool name must not be blank",
    ):
        ToolSpec(
            name=name,
            description="Read a UTF-8 text file.",
            arguments_type=ReadFileArguments,
        )


@pytest.mark.parametrize(
    "description",
    [
        "",
        " ",
        "\t",
    ],
)
def test_tool_spec_rejects_blank_description(
    description: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="tool description must not be blank",
    ):
        ToolSpec(
            name="read_file",
            description=description,
            arguments_type=ReadFileArguments,
        )


def test_tool_spec_rejects_non_string_name() -> None:
    with pytest.raises(
        TypeError,
        match="tool name must be a string",
    ):
        ToolSpec(
            name=123,
            description="Read a UTF-8 text file.",
            arguments_type=ReadFileArguments,
        )


def test_tool_spec_rejects_non_string_description() -> None:
    with pytest.raises(
        TypeError,
        match="tool description must be a string",
    ):
        ToolSpec(
            name="read_file",
            description=None,
            arguments_type=ReadFileArguments,
        )


def test_tool_spec_cannot_be_modified_after_creation() -> None:
    spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file.",
        arguments_type=ReadFileArguments,
    )

    with pytest.raises(FrozenInstanceError):
        spec.name = "write_file"
