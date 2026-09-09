"""Core records used by the memory system."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class MemoryScopeKind(StrEnum):
    """Supported memory isolation levels."""

    PROJECT = "project"
    USER = "user"


class MemoryEvidenceKind(StrEnum):
    """Sources that can support a memory."""

    USER_MESSAGE = "user_message"
    WORKSPACE_FILE = "workspace_file"
    TOOL_RESULT = "tool_result"


def _require_non_blank_string(
    *,
    field_name: str,
    value: object,
) -> str:
    """Validate one required text field."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")

    return value


def _normalize_timestamp(
    *,
    field_name: str,
    value: object,
) -> float:
    """Validate and normalize one timestamp."""
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(f"{field_name} must be a number")

    normalized = float(value)

    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")

    return normalized


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Identify where a memory may be used."""

    kind: MemoryScopeKind
    key: str

    def __post_init__(self) -> None:
        """Validate the memory scope."""
        if not isinstance(
            self.kind,
            MemoryScopeKind,
        ):
            raise TypeError("kind must be a MemoryScopeKind")

        _require_non_blank_string(
            field_name="key",
            value=self.key,
        )


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """Describe the source supporting a memory."""

    kind: MemoryEvidenceKind
    reference: str
    excerpt: str

    def __post_init__(self) -> None:
        """Validate evidence metadata."""
        if not isinstance(
            self.kind,
            MemoryEvidenceKind,
        ):
            raise TypeError("kind must be a MemoryEvidenceKind")

        _require_non_blank_string(
            field_name="reference",
            value=self.reference,
        )
        _require_non_blank_string(
            field_name="excerpt",
            value=self.excerpt,
        )


def _snapshot_evidence(
    evidence: object,
) -> tuple[MemoryEvidence, ...]:
    """Validate and snapshot memory evidence."""
    if not isinstance(
        evidence,
        Sequence,
    ) or isinstance(
        evidence,
        (str, bytes),
    ):
        raise TypeError("evidence must be a sequence")

    snapshot = tuple(evidence)

    if not snapshot:
        raise ValueError("memory must contain evidence")

    for item in snapshot:
        if not isinstance(
            item,
            MemoryEvidence,
        ):
            raise TypeError("evidence must contain MemoryEvidence instances")

    return snapshot


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    """An untrusted memory proposed by an extractor."""

    content: str
    scope: MemoryScope
    evidence: Sequence[MemoryEvidence]

    def __post_init__(self) -> None:
        """Validate and snapshot the candidate."""
        _require_non_blank_string(
            field_name="content",
            value=self.content,
        )

        if not isinstance(
            self.scope,
            MemoryScope,
        ):
            raise TypeError("scope must be a MemoryScope")

        object.__setattr__(
            self,
            "evidence",
            _snapshot_evidence(self.evidence),
        )


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """A verified memory candidate that may be stored."""

    content: str
    scope: MemoryScope
    evidence: Sequence[MemoryEvidence]

    def __post_init__(self) -> None:
        """Validate and snapshot the candidate."""
        _require_non_blank_string(
            field_name="content",
            value=self.content,
        )

        if not isinstance(
            self.scope,
            MemoryScope,
        ):
            raise TypeError("scope must be a MemoryScope")

        object.__setattr__(
            self,
            "evidence",
            _snapshot_evidence(self.evidence),
        )


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """A stored memory with lifecycle metadata."""

    memory_id: str
    content: str
    scope: MemoryScope
    evidence: Sequence[MemoryEvidence]
    created_at: float
    expires_at: float | None = None

    def __post_init__(self) -> None:
        """Validate and snapshot the stored record."""
        _require_non_blank_string(
            field_name="memory_id",
            value=self.memory_id,
        )
        _require_non_blank_string(
            field_name="content",
            value=self.content,
        )

        if not isinstance(
            self.scope,
            MemoryScope,
        ):
            raise TypeError("scope must be a MemoryScope")

        object.__setattr__(
            self,
            "evidence",
            _snapshot_evidence(self.evidence),
        )

        created_at = _normalize_timestamp(
            field_name="created_at",
            value=self.created_at,
        )
        object.__setattr__(
            self,
            "created_at",
            created_at,
        )

        if self.expires_at is None:
            return

        expires_at = _normalize_timestamp(
            field_name="expires_at",
            value=self.expires_at,
        )

        if expires_at <= created_at:
            raise ValueError("expires_at must be later than created_at")

        object.__setattr__(
            self,
            "expires_at",
            expires_at,
        )

    def is_expired(
        self,
        *,
        now: float,
    ) -> bool:
        """Return whether the record has expired."""
        normalized_now = _normalize_timestamp(
            field_name="now",
            value=now,
        )

        return self.expires_at is not None and normalized_now >= self.expires_at
