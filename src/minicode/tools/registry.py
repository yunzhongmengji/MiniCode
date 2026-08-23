"""Registry used to locate executable tools by name."""

from minicode.tools.base import Tool
from minicode.tools.spec import ToolSpec


class ToolRegistry:
    """Store executable tools under their declared names."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """Return an immutable snapshot of registered tool metadata."""
        return tuple(tool.spec for tool in self._tools.values())

    def register(self, tool: Tool) -> None:
        """Register a tool under the name declared by its specification."""
        name = tool.spec.name

        if name in self._tools:
            raise ValueError(f"tool '{name}' is already registered")

        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        """Return a registered tool, or None when the name is unknown."""
        return self._tools.get(name)
