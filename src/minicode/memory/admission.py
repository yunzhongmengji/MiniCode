"""Admission decisions for verified memory candidates."""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from minicode.memory.extraction import (
    MemoryExtractionRequest,
)
from minicode.memory.records import (
    MemoryCandidate,
)


class MemoryAdmissionOutcome(StrEnum):
    """Possible decisions for one verified memory candidate."""

    ADMIT = "admit"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class MemoryAdmissionDecision:
    """Explain whether one verified candidate may be stored."""

    outcome: MemoryAdmissionOutcome
    reason: str

    def __post_init__(self) -> None:
        """Validate the admission decision."""
        if not isinstance(
            self.outcome,
            MemoryAdmissionOutcome,
        ):
            raise TypeError(
                "outcome must be a "
                "MemoryAdmissionOutcome"
            )

        if not isinstance(
            self.reason,
            str,
        ):
            raise TypeError(
                "reason must be a string"
            )

        if not self.reason.strip():
            raise ValueError(
                "reason must not be blank"
            )


class MemoryAdmissionPolicy(Protocol):
    """Decide whether a verified candidate is worth storing."""

    async def decide(
        self,
        candidate: MemoryCandidate,
        request: MemoryExtractionRequest,
    ) -> MemoryAdmissionDecision:
        """Return the admission decision for one candidate."""
        ...


class ScriptedMemoryAdmissionPolicy:
    """Return prepared decisions for deterministic tests."""

    def __init__(
        self,
        decisions: Sequence[MemoryAdmissionDecision],
    ) -> None:
        if not isinstance(
            decisions,
            Sequence,
        ) or isinstance(
            decisions,
            (str, bytes),
        ):
            raise TypeError(
                "decisions must be a sequence"
            )

        for decision in decisions:
            if not isinstance(
                decision,
                MemoryAdmissionDecision,
            ):
                raise TypeError(
                    "decisions must contain only "
                    "MemoryAdmissionDecision instances"
                )

        self._decisions = deque(decisions)
        self._calls: list[
            tuple[
                MemoryCandidate,
                MemoryExtractionRequest,
            ]
        ] = []

    @property
    def calls(
        self,
    ) -> tuple[
        tuple[
            MemoryCandidate,
            MemoryExtractionRequest,
        ],
        ...,
    ]:
        """Return candidates and requests received by the policy."""
        return tuple(self._calls)

    async def decide(
        self,
        candidate: MemoryCandidate,
        request: MemoryExtractionRequest,
    ) -> MemoryAdmissionDecision:
        """Record the call and return the next prepared decision."""
        self._calls.append(
            (
                candidate,
                request,
            )
        )

        if not self._decisions:
            raise RuntimeError(
                "scripted memory admission policy "
                "has no decisions remaining"
            )

        return self._decisions.popleft()