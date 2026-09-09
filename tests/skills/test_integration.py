import json
from pathlib import Path

import pytest

from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
)
from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop
from minicode.models.scripted import ScriptedModel
from minicode.skills.context import (
    SkillContextBuilder,
)
from minicode.skills.discovery import (
    FileSkillCatalogLoader,
)
from minicode.skills.loader import (
    FileSkillLoader,
)
from minicode.skills.router import (
    KeywordSkillRouter,
)
from minicode.workspace import Workspace


def _write_manifest(
    *,
    skills_root: Path,
    name: str,
    description: str,
    tags: list[str],
) -> Path:
    skill_directory = skills_root / name
    skill_directory.mkdir(
        parents=True,
    )

    (skill_directory / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "description": description,
                "entrypoint": "SKILL.md",
                "tags": tags,
            }
        ),
        encoding="utf-8",
    )

    return skill_directory


@pytest.mark.asyncio
async def test_discovered_skill_reaches_query_loop_lazily(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"

    documentation_directory = _write_manifest(
        skills_root=skills_root,
        name="documentation",
        description=("Write and maintain project documentation."),
        tags=["writing"],
    )
    (documentation_directory / "SKILL.md").write_bytes(b"\xff")

    testing_directory = _write_manifest(
        skills_root=skills_root,
        name="pytest-debugging",
        description=("Diagnose Python pytest test failures."),
        tags=[
            "pytest",
            "testing",
        ],
    )
    (testing_directory / "SKILL.md").write_text(
        ("Run the smallest failing test first."),
        encoding="utf-8",
    )

    skill_workspace = Workspace(
        root=skills_root,
    )
    catalog = await FileSkillCatalogLoader(
        skill_root=skill_workspace,
    ).load()

    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    context_builder = SkillContextBuilder(
        router=KeywordSkillRouter(
            catalog=catalog,
            max_skills=1,
        ),
        loader=FileSkillLoader(
            skill_root=skill_workspace,
        ),
        event_ledger=ledger,
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="Test fixed.",
            ),
        ),
    )
    loop = QueryLoop(
        model=model,
        event_ledger=ledger,
        skill_context_provider=(context_builder),
    )
    user_message = Message(
        role=MessageRole.USER,
        content=("Fix the failing pytest test."),
    )

    result = await loop.run((user_message,))

    assert tuple(manifest.name for manifest in catalog.manifests) == (
        "documentation",
        "pytest-debugging",
    )

    assert model.requests[0].instructions == (
        (
            "# Loaded Skills\n"
            "\n"
            "## Skill: pytest-debugging\n"
            "\n"
            "Run the smallest failing "
            "test first."
        ),
    )

    assert model.requests[0].conversation == (user_message,)
    assert result.message_history == (user_message,)

    assert tuple(event.kind for event in ledger.events) == (
        EventKind.RUN_STARTED,
        EventKind.SKILL_SELECTION_FINISHED,
        EventKind.SKILL_LOAD_STARTED,
        EventKind.SKILL_LOAD_FINISHED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.RUN_FINISHED,
    )
