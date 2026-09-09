import pytest

from minicode.skills.manifest import (
    SkillManifest,
)


def test_skill_manifest_preserves_metadata() -> None:
    tags = [
        "python",
        "testing",
    ]

    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose and repair Python test failures."),
        entrypoint="SKILL.md",
        tags=tags,
    )

    tags.append("changed")

    assert manifest.name == "pytest-debugging"
    assert manifest.description == ("Diagnose and repair Python test failures.")
    assert manifest.entrypoint == "SKILL.md"
    assert manifest.tags == (
        "python",
        "testing",
    )


def test_skill_manifest_rejects_ambiguous_metadata() -> None:
    with pytest.raises(
        ValueError,
        match="name must not be blank",
    ):
        SkillManifest(
            name=" ",
            description="Diagnose test failures.",
            entrypoint="SKILL.md",
        )

    with pytest.raises(
        TypeError,
        match="tags must be a sequence",
    ):
        SkillManifest(
            name="pytest-debugging",
            description="Diagnose test failures.",
            entrypoint="SKILL.md",
            tags="python",
        )

    with pytest.raises(
        ValueError,
        match="tags must be unique",
    ):
        SkillManifest(
            name="pytest-debugging",
            description="Diagnose test failures.",
            entrypoint="SKILL.md",
            tags=(
                "python",
                "python",
            ),
        )
