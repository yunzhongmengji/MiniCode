import pytest

from minicode.tools.base import Tool
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class EchoArguments(ToolArguments):
    """Arguments accepted by the test echo tool."""

    text: str


class EchoTool:
    """Small executable tool used to test the registry."""

    @property
    def spec(self) -> ToolSpec:
        """Return metadata describing the echo tool."""
        return ToolSpec(
            name="echo",
            description="Return the supplied text.",
            arguments_type=EchoArguments,
        )

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Return validated arguments as JSON."""
        return arguments.model_dump_json()


class UppercaseTool(EchoTool):
    """Second tool used to test registry ordering."""

    @property
    def spec(self) -> ToolSpec:
        """Return metadata describing the uppercase tool."""
        return ToolSpec(
            name="uppercase",
            description="Convert supplied text to uppercase.",
            arguments_type=EchoArguments,
        )


def test_registry_returns_registered_tool_by_name() -> None:
    registry = ToolRegistry()
    tool: Tool = EchoTool()

    registry.register(tool)

    assert registry.get("echo") is tool


def test_registry_returns_none_for_unknown_tool() -> None:
    registry = ToolRegistry()

    assert registry.get("missing") is None


def test_registry_rejects_duplicate_tool_name() -> None:
    registry = ToolRegistry()
    original_tool: Tool = EchoTool()
    duplicate_tool: Tool = EchoTool()

    registry.register(original_tool)

    with pytest.raises(
        ValueError,
        match="tool 'echo' is already registered",
    ):
        registry.register(duplicate_tool)

    assert registry.get("echo") is original_tool


def test_registry_exposes_specs_in_registration_order() -> None:
    registry = ToolRegistry()
    echo_tool: Tool = EchoTool()
    uppercase_tool: Tool = UppercaseTool()

    registry.register(echo_tool)
    registry.register(uppercase_tool)

    assert registry.specs == (
        echo_tool.spec,
        uppercase_tool.spec,
    )
