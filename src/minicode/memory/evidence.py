"""Verification of evidence claimed by memory extractors."""

from typing import Protocol

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.tool_calls import ToolResult
from minicode.memory.extraction import (
    MemoryExtractionRequest,
)
from minicode.memory.records import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceKind,
    MemoryProposal,
)


class MemoryEvidenceVerificationError(ValueError):
    """Raised when claimed evidence cannot be verified."""


class MemoryEvidenceVerifier(Protocol):
    """Verify a proposal against one completed run."""

    def verify(
        self,
        proposal: MemoryProposal,
        request: MemoryExtractionRequest,
    ) -> MemoryCandidate:
        """Return a candidate only after verifying its evidence."""
        ...


def _user_message_source(
    evidence: MemoryEvidence,
    request: MemoryExtractionRequest,
) -> str:
    """Resolve a user-message evidence reference."""
    message_number = 0

    for item in request.message_history:
        if (
            not isinstance(
                item,
                Message,
            )
            or item.role is not MessageRole.USER
        ):
            continue

        message_number += 1
        reference = f"{request.run_id}:message_{message_number:03d}"

        if evidence.reference == reference:
            return item.content

    raise MemoryEvidenceVerificationError(
        f"user-message evidence reference was not found: {evidence.reference}"
    )


def _tool_result_source(
    evidence: MemoryEvidence,
    request: MemoryExtractionRequest,
) -> str:
    """Resolve a tool-result evidence reference."""
    for item in request.message_history:
        if not isinstance(
            item,
            ToolResult,
        ):
            continue

        reference = f"{request.run_id}:{item.call_id}"

        if evidence.reference == reference:
            return item.output

    raise MemoryEvidenceVerificationError(
        f"tool-result evidence reference was not found: {evidence.reference}"
    )


class RunEvidenceVerifier:
    """Verify evidence present in a completed run snapshot."""

    def verify(
        self,
        proposal: MemoryProposal,
        request: MemoryExtractionRequest,
    ) -> MemoryCandidate:
        """Verify all evidence before creating a candidate."""
        for evidence in proposal.evidence:
            if evidence.kind is MemoryEvidenceKind.USER_MESSAGE:
                source = _user_message_source(
                    evidence,
                    request,
                )
            elif evidence.kind is MemoryEvidenceKind.TOOL_RESULT:
                source = _tool_result_source(
                    evidence,
                    request,
                )
            else:
                raise MemoryEvidenceVerificationError(
                    "workspace-file evidence requires artifact-backed verification"
                )

            if evidence.excerpt not in source:
                raise MemoryEvidenceVerificationError(
                    "memory evidence excerpt does not "
                    f"match source: {evidence.reference}"
                )

        return MemoryCandidate(
            content=proposal.content,
            scope=proposal.scope,
            evidence=proposal.evidence,
        )
