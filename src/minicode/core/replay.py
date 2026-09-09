"""Reconstruct audit summaries from ledger events."""

from collections.abc import Sequence
from dataclasses import dataclass

from minicode.core.events import (
    EventKind,
    LedgerEvent,
)


@dataclass(frozen=True, slots=True)
class RunReplay:
    """Validated, read-only replay of one run."""

    events: Sequence[LedgerEvent]

    def __post_init__(self) -> None:
        """Validate and snapshot the event stream."""
        if not isinstance(
            self.events,
            Sequence,
        ) or isinstance(
            self.events,
            (str, bytes),
        ):
            raise TypeError("events must be a sequence")

        if not self.events:
            raise ValueError("events must not be empty")

        first_event = self.events[0]

        if not isinstance(
            first_event,
            LedgerEvent,
        ):
            raise TypeError("events must contain only LedgerEvent instances")

        run_id = first_event.run_id

        for expected_sequence, event in enumerate(
            self.events,
            start=1,
        ):
            if not isinstance(
                event,
                LedgerEvent,
            ):
                raise TypeError("events must contain only LedgerEvent instances")

            if event.run_id != run_id:
                raise ValueError("events must belong to one run")

            if event.sequence != expected_sequence:
                raise ValueError("event sequences must be contiguous and start at one")

        if first_event.kind not in (
            EventKind.RUN_STARTED,
            EventKind.RUN_RESUMED,
        ):
            raise ValueError("replay must start with a run boundary event")

        if self.events[-1].kind is EventKind.RUN_FINISHED:
            outcome = self.events[-1].payload.get("outcome")

            if not isinstance(
                outcome,
                str,
            ):
                raise ValueError("finished run event must contain a string outcome")

        object.__setattr__(
            self,
            "events",
            tuple(self.events),
        )

    @property
    def run_id(self) -> str:
        """Return the replayed run identifier."""
        return self.events[0].run_id

    @property
    def is_finished(self) -> bool:
        """Return whether the latest segment finished."""
        return self.events[-1].kind is EventKind.RUN_FINISHED

    @property
    def outcome(self) -> str | None:
        """Return the latest completed outcome."""
        if not self.is_finished:
            return None

        outcome = self.events[-1].payload["outcome"]

        if not isinstance(
            outcome,
            str,
        ):
            raise TypeError("validated outcome is not a string")

        return outcome

    @property
    def model_call_count(self) -> int:
        """Count model-call attempts."""
        return sum(event.kind is EventKind.MODEL_CALL_STARTED for event in self.events)

    @property
    def tool_execution_count(self) -> int:
        """Count tool-execution attempts."""
        return sum(
            event.kind is EventKind.TOOL_EXECUTION_STARTED for event in self.events
        )

    @property
    def checkpoint_count(self) -> int:
        """Count saved checkpoints."""
        return sum(event.kind is EventKind.CHECKPOINT_SAVED for event in self.events)

    @property
    def failed_tool_call_ids(
        self,
    ) -> tuple[str, ...]:
        """Return tool calls that finished as failed."""
        failed_call_ids: list[str] = []

        for event in self.events:
            if event.kind is not EventKind.TOOL_EXECUTION_FINISHED:
                continue

            if event.payload.get("outcome") != "failed":
                continue

            call_id = event.payload.get("call_id")

            if not isinstance(
                call_id,
                str,
            ):
                raise TypeError("failed tool event must contain a string call_id")

            failed_call_ids.append(call_id)

        return tuple(failed_call_ids)
