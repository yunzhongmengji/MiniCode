from minicode.core.artifacts import (
    ArtifactRef,
    ArtifactStore,
    InMemoryArtifactStore,
)


def accepts_artifact_store(
    store: ArtifactStore,
) -> None:
    reference = store.put_text(
        "MiniCode",
        media_type="text/plain",
    )
    content = store.read_text(reference.artifact_id)

    assert_type_reference: ArtifactRef = reference
    assert_type_content: str = content

    del (
        assert_type_reference,
        assert_type_content,
    )


in_memory_store = InMemoryArtifactStore()

accepts_artifact_store(in_memory_store)
