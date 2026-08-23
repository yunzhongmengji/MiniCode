"""Contract implemented by executable MiniCode tools."""

from typing import Protocol

from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class ToolExecutionError(Exception):
    """Expected tool failure whose message is safe to return to the model."""


class Tool(Protocol):
    """Executable capability managed by MiniCode's tool runtime."""

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        ...

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Execute validated arguments and return textual output."""
        ...
