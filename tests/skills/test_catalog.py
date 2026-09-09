import pytest

from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.manifest import (
    SkillManifest,
)


def _make_manifest(
    name: str,
) -> SkillManifest:
    return SkillManifest(
        name=name,
        description=f"Instructions for {name}.",
        entrypoint="SKILL.md",
        tags=(name,),
    )


def test_skill_catalog_registers_and_exposes_manifests() -> None:
    catalog = SkillCatalog()
    testing = _make_manifest("pytest-debugging")
    documentation = _make_manifest("documentation-writing")

    catalog.register(testing)
    catalog.register(documentation)

    assert catalog.get("pytest-debugging") is testing
    assert catalog.get("documentation-writing") is documentation
    assert catalog.get("missing") is None
    assert catalog.manifests == (
        testing,
        documentation,
    )


def test_skill_catalog_rejects_duplicate_name() -> None:
    catalog = SkillCatalog()
    original = _make_manifest("pytest-debugging")
    duplicate = SkillManifest(
        name="pytest-debugging",
        description="A different description.",
        entrypoint="OTHER.md",
    )

    catalog.register(original)

    with pytest.raises(
        ValueError,
        match=("skill 'pytest-debugging' is already registered"),
    ):
        catalog.register(duplicate)

    assert catalog.get("pytest-debugging") is original
