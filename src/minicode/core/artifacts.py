"""Artifact references and storage contracts."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol


class ArtifactError(RuntimeError):
    """Base exception for artifact storage failures."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when a requested artifact does not exist."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Metadata identifying one stored artifact."""

    artifact_id: str
    media_type: str
    byte_count: int

    def __post_init__(self) -> None:
        """Validate artifact reference metadata."""
        text_fields = (
            (
                "artifact_id",
                self.artifact_id,
            ),
            (
                "media_type",
                self.media_type,
            ),
        )

        for field_name, value in text_fields:
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if type(self.byte_count) is not int:
            raise TypeError("byte_count must be an integer")

        if self.byte_count < 0:
            raise ValueError("byte_count must not be negative")


class ArtifactStore(Protocol):
    """Store and retrieve text artifacts."""

    def put_text(
        self,
        content: str,
        *,
        media_type: str,
    ) -> ArtifactRef:
        """Store text and return its reference."""
        ...

    def read_text(
        self,
        artifact_id: str,
    ) -> str:
        """Read stored text by artifact identifier."""
        ...


class InMemoryArtifactStore:
    """Store UTF-8 text artifacts in process memory."""

    def __init__(self) -> None:
        self._content_by_id: dict[
            str,
            bytes,
        ] = {}

    def put_text(
        self,
        content: str,
        *,
        media_type: str,
    ) -> ArtifactRef:
        """Store text and return its content-addressed reference."""
        if not isinstance(content, str):
            raise TypeError("content must be a string")

        encoded_content = content.encode("utf-8")
        artifact_id = f"sha256:{sha256(encoded_content).hexdigest()}"
        reference = ArtifactRef(
            artifact_id=artifact_id,
            media_type=media_type,
            byte_count=len(encoded_content),
        )

        self._content_by_id.setdefault(
            artifact_id,
            encoded_content,
        )

        return reference

    def read_text(
        self,
        artifact_id: str,
    ) -> str:
        """Read one stored UTF-8 text artifact."""
        try:
            encoded_content = self._content_by_id[artifact_id]
        except KeyError:
            raise ArtifactNotFoundError(f"artifact not found: {artifact_id}") from None

        return encoded_content.decode("utf-8")
