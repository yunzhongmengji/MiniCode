"""Provider-neutral audit events for MiniCode runs."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from minicode.core.tool_calls import JsonValue


def _freeze_payload_value(
    value: object,
) -> JsonValue:
    """Validate and recursively freeze one payload value."""
    if isinstance(
        value,
        float,
    ) and not math.isfinite(value):
        raise ValueError("payload numbers must be finite")

    if value is None or isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, Mapping):
        frozen_items: dict[str, JsonValue] = {}

        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("payload keys must be strings")

            frozen_items[key] = _freeze_payload_value(item)

        return MappingProxyType(frozen_items)

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return tuple(_freeze_payload_value(item) for item in value)

    raise TypeError("payload must contain only JSON-compatible values")


def _validate_run_id(
    value: object,
) -> str:
    """Validate and return one run identifier."""
    if not isinstance(value, str):
        raise TypeError("run_id must be a string")

    if not value.strip():
        raise ValueError("run_id must not be blank")

    return value


class EventKind(StrEnum):
    """Stable kinds of facts recorded during one run."""

    RUN_STARTED = "run_started"
    RUN_RESUMED = "run_resumed"
    SKILL_SELECTION_FINISHED = "skill_selection_finished"
    SKILL_LOAD_STARTED = "skill_load_started"
    SKILL_LOAD_FINISHED = "skill_load_finished"
    MEMORY_RETRIEVAL_FINISHED = "memory_retrieval_finished"
    MODEL_CALL_STARTED = "model_call_started"
    MODEL_CALL_FINISHED = "model_call_finished"
    TOOL_POLICY_DECIDED = "tool_policy_decided"
    TOOL_APPROVAL_RESOLVED = "tool_approval_resolved"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_FINISHED = "tool_execution_finished"
    CHECKPOINT_SAVED = "checkpoint_saved"
    RUN_FINISHED = "run_finished"


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """One ordered audit fact from a MiniCode run."""

    run_id: str
    sequence: int
    kind: EventKind
    payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """Validate identity and freeze event payload."""
        _validate_run_id(self.run_id)

        if type(self.sequence) is not int:
            raise TypeError("sequence must be an integer")

        if self.sequence <= 0:
            raise ValueError("sequence must be greater than zero")

        if not isinstance(
            self.kind,
            EventKind,
        ):
            raise TypeError("kind must be an EventKind")

        if not isinstance(
            self.payload,
            Mapping,
        ):
            raise TypeError("payload must be a mapping")

        frozen_payload: dict[
            str,
            JsonValue,
        ] = {}

        for key, value in self.payload.items():
            if not isinstance(key, str):
                raise TypeError("payload keys must be strings")

            frozen_payload[key] = _freeze_payload_value(value)

        object.__setattr__(
            self,
            "payload",
            MappingProxyType(frozen_payload),
        )


class EventLedger(Protocol):
    """Record ordered audit events for one run."""

    @property
    def run_id(self) -> str:
        """Return the run identifier."""
        ...

    def record(
        self,
        kind: EventKind,
        payload: Mapping[str, JsonValue],
    ) -> LedgerEvent:
        """Record and return the next event."""
        ...


class InMemoryEventLedger:
    """Store one run's events in append-only order."""

    def __init__(
        self,
        *,
        run_id: str,
    ) -> None:
        self._run_id = _validate_run_id(run_id)
        self._events: list[LedgerEvent] = []

    @property
    def run_id(self) -> str:
        """Return the run identifier."""
        return self._run_id

    @property
    def events(
        self,
    ) -> tuple[LedgerEvent, ...]:
        """Return an immutable event snapshot."""
        return tuple(self._events)

    def record(
        self,
        kind: EventKind,
        payload: Mapping[str, JsonValue],
    ) -> LedgerEvent:
        """Create and append the next ordered event."""
        event = LedgerEvent(
            run_id=self._run_id,
            sequence=len(self._events) + 1,
            kind=kind,
            payload=payload,
        )

        self._events.append(event)

        return event
