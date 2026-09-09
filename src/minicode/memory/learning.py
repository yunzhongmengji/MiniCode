"""Coordination of extraction and memory admission."""

from collections.abc import Sequence
from dataclasses import dataclass

from minicode.memory.admission import (
    MemoryAdmissionDecision,
    MemoryAdmissionOutcome,
)
from minicode.memory.evidence import (
    MemoryEvidenceVerifier,
)
from minicode.memory.extraction import (
    MemoryExtractionRequest,
    MemoryExtractor,
)
from minicode.memory.records import (
    MemoryCandidate,
    MemoryProposal,
)
from minicode.memory.service import (
    MemoryService,
    MemoryWriteResult,
)


class MemoryLearningError(RuntimeError):
    """Base exception for memory learning failures."""


class MemoryScopeMismatchError(MemoryLearningError):
    """Raised when extracted memory crosses its scope."""


@dataclass(frozen=True, slots=True)
class MemoryLearningItemResult:
    """Learning result for one extracted proposal."""

    proposal: MemoryProposal
    candidate: MemoryCandidate | None
    decision: MemoryAdmissionDecision
    write: MemoryWriteResult | None

    def __post_init__(self) -> None:
        """Validate relationships between result fields."""
        if not isinstance(
            self.proposal,
            MemoryProposal,
        ):
            raise TypeError("proposal must be a MemoryProposal")

        if self.candidate is not None and not isinstance(
            self.candidate,
            MemoryCandidate,
        ):
            raise TypeError("candidate must be a MemoryCandidate or None")

        if not isinstance(
            self.decision,
            MemoryAdmissionDecision,
        ):
            raise TypeError("decision must be a MemoryAdmissionDecision")

        if self.write is not None and not isinstance(
            self.write,
            MemoryWriteResult,
        ):
            raise TypeError("write must be a MemoryWriteResult or None")

        if self.decision.outcome is MemoryAdmissionOutcome.REJECT:
            if self.write is not None:
                raise ValueError("rejected memory must not have a write result")

            return

        if self.candidate is None:
            raise ValueError("admitted memory must have a verified candidate")

        if self.write is None:
            raise ValueError("admitted memory must have a write result")


@dataclass(frozen=True, slots=True)
class MemoryLearningResult:
    """Results for all proposals extracted from one run."""

    items: Sequence[MemoryLearningItemResult]

    def __post_init__(self) -> None:
        """Validate and snapshot item results."""
        items = tuple(self.items)

        for item in items:
            if not isinstance(
                item,
                MemoryLearningItemResult,
            ):
                raise TypeError(
                    "items must contain only MemoryLearningItemResult instances"
                )

        object.__setattr__(
            self,
            "items",
            items,
        )

    @property
    def proposals(
        self,
    ) -> tuple[MemoryProposal, ...]:
        """Return all extracted proposals."""
        return tuple(item.proposal for item in self.items)

    @property
    def candidates(
        self,
    ) -> tuple[MemoryCandidate, ...]:
        """Return proposals that passed evidence verification."""
        return tuple(
            item.candidate for item in self.items if item.candidate is not None
        )

    @property
    def writes(
        self,
    ) -> tuple[MemoryWriteResult, ...]:
        """Return completed memory writes."""
        return tuple(item.write for item in self.items if item.write is not None)


class MemoryLearner:
    """Extract and admit memories from one run."""

    def __init__(
        self,
        *,
        extractor: MemoryExtractor,
        evidence_verifier: (MemoryEvidenceVerifier),
        service: MemoryService,
    ) -> None:
        self._extractor = extractor
        self._evidence_verifier = evidence_verifier
        self._service = service

    async def learn(
        self,
        request: MemoryExtractionRequest,
        *,
        ttl_seconds: float | None = None,
    ) -> MemoryLearningResult:
        """Extract, validate, and save memory candidates."""
        proposals = await self._extractor.extract(request)

        for proposal in proposals:
            if not isinstance(
                proposal,
                MemoryProposal,
            ):
                raise TypeError("extractor must return MemoryProposal instances")

            if proposal.scope != request.scope:
                raise MemoryScopeMismatchError(
                    "extracted memory scope does not match request scope"
                )

        candidates = tuple(
            self._evidence_verifier.verify(
                proposal,
                request,
            )
            for proposal in proposals
        )

        writes = tuple(
            self._service.remember(
                candidate,
                ttl_seconds=ttl_seconds,
            )
            for candidate in candidates
        )

        return MemoryLearningResult(
            items=tuple(
                MemoryLearningItemResult(
                    proposal=proposal,
                    candidate=candidate,
                    decision=(
                        MemoryAdmissionDecision(
                            outcome=(MemoryAdmissionOutcome.ADMIT),
                            reason=(
                                "verified candidate admitted by the current pipeline"
                            ),
                        )
                    ),
                    write=write,
                )
                for proposal, candidate, write in zip(
                    proposals,
                    candidates,
                    writes,
                    strict=True,
                )
            ),
        )
