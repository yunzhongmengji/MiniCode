from hashlib import sha256

import pytest

from minicode.core.artifacts import (
    ArtifactNotFoundError,
    ArtifactRef,
    InMemoryArtifactStore,
)


def test_artifact_ref_preserves_metadata() -> None:
    reference = ArtifactRef(
        artifact_id="sha256:abc123",
        media_type="text/plain",
        byte_count=12,
    )

    assert reference.artifact_id == ("sha256:abc123")
    assert reference.media_type == ("text/plain")
    assert reference.byte_count == 12


def test_artifact_ref_validates_metadata() -> None:
    with pytest.raises(
        TypeError,
        match="artifact_id must be a string",
    ):
        ArtifactRef(
            artifact_id=17,  # type: ignore[arg-type]
            media_type="text/plain",
            byte_count=12,
        )

    with pytest.raises(
        ValueError,
        match="artifact_id must not be blank",
    ):
        ArtifactRef(
            artifact_id=" ",
            media_type="text/plain",
            byte_count=12,
        )

    with pytest.raises(
        TypeError,
        match="media_type must be a string",
    ):
        ArtifactRef(
            artifact_id="sha256:abc123",
            media_type=None,  # type: ignore[arg-type]
            byte_count=12,
        )

    with pytest.raises(
        ValueError,
        match="media_type must not be blank",
    ):
        ArtifactRef(
            artifact_id="sha256:abc123",
            media_type="\t",
            byte_count=12,
        )

    with pytest.raises(
        TypeError,
        match="byte_count must be an integer",
    ):
        ArtifactRef(
            artifact_id="sha256:abc123",
            media_type="text/plain",
            byte_count=True,
        )

    with pytest.raises(
        ValueError,
        match="byte_count must not be negative",
    ):
        ArtifactRef(
            artifact_id="sha256:abc123",
            media_type="text/plain",
            byte_count=-1,
        )


def test_in_memory_artifact_store_round_trips_text() -> None:
    store = InMemoryArtifactStore()
    content = "MiniCode 你好"
    encoded_content = content.encode("utf-8")

    reference = store.put_text(
        content,
        media_type="text/plain",
    )

    assert reference == ArtifactRef(
        artifact_id=(f"sha256:{sha256(encoded_content).hexdigest()}"),
        media_type="text/plain",
        byte_count=len(encoded_content),
    )
    assert store.read_text(reference.artifact_id) == content

    duplicate_reference = store.put_text(
        content,
        media_type="text/plain",
    )

    assert duplicate_reference == reference


def test_artifact_store_rejects_non_string_content() -> None:
    store = InMemoryArtifactStore()

    with pytest.raises(
        TypeError,
        match="content must be a string",
    ):
        store.put_text(
            17,  # type: ignore[arg-type]
            media_type="text/plain",
        )


def test_artifact_store_does_not_write_invalid_artifact() -> None:
    store = InMemoryArtifactStore()
    content = "must not be stored"
    encoded_content = content.encode("utf-8")
    artifact_id = f"sha256:{sha256(encoded_content).hexdigest()}"

    with pytest.raises(
        ValueError,
        match="media_type must not be blank",
    ):
        store.put_text(
            content,
            media_type=" ",
        )

    with pytest.raises(
        ArtifactNotFoundError,
        match=f"artifact not found: {artifact_id}",
    ):
        store.read_text(artifact_id)


def test_artifact_store_reports_missing_artifact() -> None:
    store = InMemoryArtifactStore()

    with pytest.raises(
        ArtifactNotFoundError,
        match=("artifact not found: sha256:missing"),
    ):
        store.read_text("sha256:missing")
