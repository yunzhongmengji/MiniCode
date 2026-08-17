"""Tool-call data exchanged by MiniCode components."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

type JsonScalar = str | int | float | bool | None
type JsonValue = (
    JsonScalar | Mapping[str, JsonValue] | list[JsonValue] | tuple[JsonValue, ...]
)


def _freeze_value(value: object) -> JsonValue:
    """Validate and recursively copy values into read-only structures."""

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("tool argument numbers must be finite")

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Mapping):
        frozen_items: dict[str, JsonValue] = {}

        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("tool argument keys must be strings")

            frozen_items[key] = _freeze_value(item)

        return MappingProxyType(frozen_items)

    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)

    raise TypeError("tool arguments must contain only JSON-compatible values")


def _validate_string(value: object, field_name: str) -> str:
    """Require a field to be a string."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    return value


def _validate_non_blank_string(value: object, field_name: str) -> None:
    """Require a string field to contain non-whitespace characters."""
    string_value = _validate_string(value, field_name)

    if not string_value.strip():
        raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model-proposed request to invoke a named tool."""

    call_id: str
    name: str
    arguments: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """Validate and freeze the proposed tool call."""
        _validate_non_blank_string(self.call_id, "call_id")
        _validate_non_blank_string(self.name, "name")

        if not isinstance(self.arguments, Mapping):
            raise TypeError("tool arguments must be a mapping")

        frozen_arguments = _freeze_value(self.arguments)
        object.__setattr__(self, "arguments", frozen_arguments)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The output of a tool execution paired with its ToolCall."""

    call_id: str
    output: str
    is_error: bool = False

    def __post_init__(self) -> None:
        """Validate the tool result."""
        _validate_non_blank_string(self.call_id, "call_id")
        _validate_string(self.output, "output")

        if not isinstance(self.is_error, bool):
            raise TypeError("is_error must be a boolean")
