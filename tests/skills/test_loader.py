from pathlib import Path

import pytest

from minicode.skills.loader import (
    FileSkillLoader,
    LoadedSkill,
    SkillLoadError,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.workspace import Workspace


@pytest.mark.asyncio
async def test_file_skill_loader_reads_selected_instructions(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"
    skill_directory = skills_root / "pytest-debugging"
    skill_directory.mkdir(
        parents=True,
    )
    instructions = "# Pytest Debugging\n\nRun the smallest failing test first.\n"
    (skill_directory / "SKILL.md").write_text(
        instructions,
        encoding="utf-8",
    )
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
        tags=("pytest",),
    )
    loader = FileSkillLoader(
        skill_root=Workspace(
            root=skills_root,
        ),
    )

    loaded = await loader.load(manifest)

    assert loaded == LoadedSkill(
        manifest=manifest,
        instructions=instructions,
    )


@pytest.mark.asyncio
async def test_file_skill_loader_rejects_cross_skill_escape(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"
    testing_directory = skills_root / "pytest-debugging"
    other_directory = skills_root / "other-skill"
    testing_directory.mkdir(
        parents=True,
    )
    other_directory.mkdir()
    (other_directory / "SKILL.md").write_text(
        "Instructions belonging to another skill.",
        encoding="utf-8",
    )
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="../other-skill/SKILL.md",
    )
    loader = FileSkillLoader(
        skill_root=Workspace(
            root=skills_root,
        ),
    )

    with pytest.raises(
        SkillLoadError,
        match=("skill 'pytest-debugging' entrypoint escapes its directory"),
    ) as exc_info:
        await loader.load(manifest)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )


@pytest.mark.asyncio
async def test_file_skill_loader_enforces_byte_limit(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"
    skill_directory = skills_root / "pytest-debugging"
    skill_directory.mkdir(
        parents=True,
    )
    (skill_directory / "SKILL.md").write_text(
        "123456",
        encoding="utf-8",
    )
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
    )
    loader = FileSkillLoader(
        skill_root=Workspace(
            root=skills_root,
        ),
        max_bytes=5,
    )

    with pytest.raises(
        SkillLoadError,
        match=("skill 'pytest-debugging' exceeds the 5-byte limit"),
    ):
        await loader.load(manifest)
