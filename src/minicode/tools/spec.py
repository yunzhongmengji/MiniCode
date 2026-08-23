"""Metadata describing tools exposed by MiniCode."""

from dataclasses import dataclass

from minicode.tools.schema import ToolArguments


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Describe a tool without executing it."""

    name: str
    description: str
    arguments_type: type[ToolArguments]

    def __post_init__(self) -> None:
        """Validate tool metadata after initialization."""
        if not isinstance(self.name, str):
            raise TypeError("tool name must be a string")

        if not self.name.strip():
            raise ValueError("tool name must not be blank")

        if not isinstance(self.description, str):
            raise TypeError("tool description must be a string")

        if not self.description.strip():
            raise ValueError("tool description must not be blank")

        if not isinstance(self.arguments_type, type) or not issubclass(
            self.arguments_type,
            ToolArguments,
        ):
            raise TypeError("arguments_type must be a ToolArguments subclass")
