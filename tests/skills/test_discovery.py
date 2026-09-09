import json
from pathlib import Path

import pytest

from minicode.skills.discovery import (
    FileSkillCatalogLoader,
    SkillCatalogLoadError,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.workspace import Workspace


def _write_skill(
    *,
    skills_root: Path,
    directory_name: str,
    manifest_name: str,
    description: str,
) -> None:
    skill_directory = skills_root / directory_name
    skill_directory.mkdir(
        parents=True,
    )
    (skill_directory / "manifest.json").write_text(
        json.dumps(
            {
                "name": manifest_name,
                "description": description,
                "entrypoint": "SKILL.md",
                "tags": [
                    manifest_name,
                ],
            }
        ),
        encoding="utf-8",
    )
    (skill_directory / "SKILL.md").write_text(
        f"Instructions for {manifest_name}.",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_file_catalog_loader_discovers_manifests_in_stable_order(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"

    _write_skill(
        skills_root=skills_root,
        directory_name="testing",
        manifest_name="testing",
        description="Diagnose test failures.",
    )
    _write_skill(
        skills_root=skills_root,
        directory_name="documentation",
        manifest_name="documentation",
        description="Write project documentation.",
    )

    loader = FileSkillCatalogLoader(
        skill_root=Workspace(
            root=skills_root,
        ),
    )

    catalog = await loader.load()

    assert catalog.manifests == (
        SkillManifest(
            name="documentation",
            description=("Write project documentation."),
            entrypoint="SKILL.md",
            tags=("documentation",),
        ),
        SkillManifest(
            name="testing",
            description=("Diagnose test failures."),
            entrypoint="SKILL.md",
            tags=("testing",),
        ),
    )


@pytest.mark.asyncio
async def test_file_catalog_loader_requires_name_to_match_directory(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"

    _write_skill(
        skills_root=skills_root,
        directory_name="pytest-debugging",
        manifest_name="different-name",
        description="Diagnose test failures.",
    )

    loader = FileSkillCatalogLoader(
        skill_root=Workspace(
            root=skills_root,
        ),
    )

    with pytest.raises(
        SkillCatalogLoadError,
        match=(
            "manifest name 'different-name' does not match directory 'pytest-debugging'"
        ),
    ):
        await loader.load()
