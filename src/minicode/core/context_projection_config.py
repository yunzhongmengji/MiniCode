"""Stable configuration documents for model-context projection."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum

from minicode.core.context_editing import validate_max_request_bytes
from minicode.core.tool_calls import JsonValue


class ContextProjectionStrategy(StrEnum):
    """Stable names for model-context projection behavior."""

    IDENTITY = "identity"
    TOOL_RESULT_REFERENCE = "tool_result_reference"
    BUDGETED_TOOL_RESULT_REFERENCE = "budgeted_tool_result_reference"
    CUSTOM = "custom"


class RetrievalToolLoading(StrEnum):
    """Stable names for when a projector exposes its retrieval tool."""

    ON_REFERENCE = "on_reference"


@dataclass(frozen=True, slots=True)
class ContextProjectionConfiguration:
    """Version-two Trace configuration used by existing projectors."""

    strategy: ContextProjectionStrategy
    max_inline_tool_result_bytes: int | None
    minimum_net_savings_bytes: int | None
    retrieval_tool_loading: RetrievalToolLoading | None

    def to_payload(self) -> dict[str, str | int | None]:
        """Return the existing schema-two configuration document."""
        return {
            "configuration_schema_version": 2,
            "strategy": self.strategy,
            "max_inline_tool_result_bytes": self.max_inline_tool_result_bytes,
            "minimum_net_savings_bytes": self.minimum_net_savings_bytes,
            "retrieval_tool_loading": self.retrieval_tool_loading,
        }


@dataclass(frozen=True, slots=True)
class BudgetedContextProjectionConfiguration:
    """Version-three configuration for one budget-driven projector."""

    max_request_bytes: int
    protected_recent_batch_count: int
    minimum_net_savings_bytes: int
    excluded_tool_names: tuple[str, ...]
    max_retrievable_output_bytes: int
    retrieval_tool_loading: RetrievalToolLoading = RetrievalToolLoading.ON_REFERENCE

    def __post_init__(self) -> None:
        """Validate and normalize every behavior-affecting parameter."""
        validate_max_request_bytes(self.max_request_bytes)
        _require_positive_integer(
            self.protected_recent_batch_count,
            "protected_recent_batch_count",
        )
        _require_positive_integer(
            self.minimum_net_savings_bytes,
            "minimum_net_savings_bytes",
        )
        _require_positive_integer(
            self.max_retrievable_output_bytes,
            "max_retrievable_output_bytes",
        )
        normalized_names = normalize_excluded_tool_names(self.excluded_tool_names)
        object.__setattr__(self, "excluded_tool_names", normalized_names)

        if self.retrieval_tool_loading is not RetrievalToolLoading.ON_REFERENCE:
            raise ValueError("retrieval_tool_loading must be on_reference")

    def to_payload(self) -> dict[str, JsonValue]:
        """Return the stable schema-three configuration document."""
        return {
            "configuration_schema_version": 3,
            "strategy": ContextProjectionStrategy.BUDGETED_TOOL_RESULT_REFERENCE,
            "max_request_bytes": self.max_request_bytes,
            "protected_recent_batch_count": self.protected_recent_batch_count,
            "minimum_net_savings_bytes": self.minimum_net_savings_bytes,
            "excluded_tool_names": list(self.excluded_tool_names),
            "max_retrievable_output_bytes": self.max_retrievable_output_bytes,
            "retrieval_tool_loading": self.retrieval_tool_loading,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "BudgetedContextProjectionConfiguration":
        """Parse one strict schema-three configuration document."""
        expected_fields = {
            "configuration_schema_version",
            "strategy",
            "max_request_bytes",
            "protected_recent_batch_count",
            "minimum_net_savings_bytes",
            "excluded_tool_names",
            "max_retrievable_output_bytes",
            "retrieval_tool_loading",
        }
        actual_fields = set(payload)

        if actual_fields != expected_fields:
            missing = sorted(expected_fields - actual_fields)
            unexpected = sorted(actual_fields - expected_fields)
            raise ValueError(
                "budgeted context configuration fields do not match schema 3: "
                f"missing={missing}, unexpected={unexpected}"
            )

        schema_version = _required_integer(payload, "configuration_schema_version")

        if schema_version != 3:
            raise ValueError(
                "unsupported budgeted context configuration schema "
                f"{schema_version}"
            )

        strategy = _required_string(payload, "strategy")

        if strategy != ContextProjectionStrategy.BUDGETED_TOOL_RESULT_REFERENCE:
            raise ValueError("strategy must be budgeted_tool_result_reference")

        loading = RetrievalToolLoading(
            _required_string(payload, "retrieval_tool_loading")
        )
        return cls(
            max_request_bytes=_required_integer(payload, "max_request_bytes"),
            protected_recent_batch_count=_required_integer(
                payload,
                "protected_recent_batch_count",
            ),
            minimum_net_savings_bytes=_required_integer(
                payload,
                "minimum_net_savings_bytes",
            ),
            excluded_tool_names=_required_string_tuple(
                payload,
                "excluded_tool_names",
            ),
            max_retrievable_output_bytes=_required_integer(
                payload,
                "max_retrievable_output_bytes",
            ),
            retrieval_tool_loading=loading,
        )


def normalize_excluded_tool_names(
    excluded_tool_names: Collection[str],
) -> tuple[str, ...]:
    """Return validated tool names in a stable order without duplicates."""
    if isinstance(excluded_tool_names, (str, bytes)) or not isinstance(
        excluded_tool_names,
        Collection,
    ):
        raise TypeError("excluded_tool_names must be a collection")

    normalized_names: set[str] = set()

    for tool_name in excluded_tool_names:
        if not isinstance(tool_name, str):
            raise TypeError("excluded_tool_names must contain only strings")

        if not tool_name.strip():
            raise ValueError("excluded_tool_names must not contain blank strings")

        normalized_names.add(tool_name)

    return tuple(sorted(normalized_names))


def _required_integer(source: Mapping[str, object], key: str) -> int:
    value = source[key]

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer")

    return value


def _required_string(source: Mapping[str, object], key: str) -> str:
    value = source[key]

    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")

    return value


def _required_string_tuple(
    source: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = source[key]

    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{key} must be an array")

    items: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{key} must contain only strings")

        items.append(item)

    return tuple(items)


def _require_positive_integer(value: object, field_name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer")

    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
