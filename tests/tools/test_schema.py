import pytest
from pydantic import ValidationError

from minicode.tools.schema import ToolArguments


class ReadFileArguments(ToolArguments):
    """Arguments used to exercise the shared tool schema."""

    path: str


class RetryArguments(ToolArguments):
    """Arguments used to test strict integer validation."""

    attempts: int


def test_tool_arguments_accept_valid_input() -> None:
    arguments = ReadFileArguments.model_validate(
        {
            "path": "README.md",
        }
    )

    assert arguments.path == "README.md"


def test_tool_arguments_reject_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReadFileArguments.model_validate(
            {
                "path": "README.md",
                "pth": "README.md",
            }
        )

    errors = exc_info.value.errors()

    assert len(errors) == 1
    assert errors[0]["type"] == "extra_forbidden"
    assert errors[0]["loc"] == ("pth",)


def test_tool_arguments_reject_type_coercion() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RetryArguments.model_validate(
            {
                "attempts": "3",
            }
        )

    errors = exc_info.value.errors()

    assert len(errors) == 1
    assert errors[0]["type"] == "int_type"
    assert errors[0]["loc"] == ("attempts",)


def test_tool_arguments_cannot_be_modified_after_validation() -> None:
    arguments = ReadFileArguments.model_validate(
        {
            "path": "README.md",
        }
    )

    with pytest.raises(ValidationError) as exc_info:
        arguments.path = "pyproject.toml"

    errors = exc_info.value.errors()

    assert len(errors) == 1
    assert errors[0]["type"] == "frozen_instance"
    assert errors[0]["loc"] == ("path",)


def test_tool_arguments_generate_json_schema() -> None:
    schema = ReadFileArguments.model_json_schema()

    assert schema["type"] == "object"
    assert schema["properties"]["path"]["type"] == "string"
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
