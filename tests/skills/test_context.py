import pytest

from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
)
from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.context import (
    SkillContext,
    SkillContextBuilder,
)
from minicode.skills.loader import (
    LoadedSkill,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.skills.router import (
    KeywordSkillRouter,
)


class RecordingSkillLoader:
    """Return generated instructions and record loads."""

    def __init__(self) -> None:
        self.calls: list[SkillManifest] = []

    async def load(
        self,
        manifest: SkillManifest,
    ) -> LoadedSkill:
        self.calls.append(manifest)

        return LoadedSkill(
            manifest=manifest,
            instructions=(f"Instructions for {manifest.name}."),
        )


@pytest.mark.asyncio
async def test_skill_context_builder_loads_ranked_selection() -> None:
    documentation = SkillManifest(
        name="docs",
        description=("Write project documentation."),
        entrypoint="SKILL.md",
    )
    testing = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
    )
    catalog = SkillCatalog()
    catalog.register(documentation)
    catalog.register(testing)

    loader = RecordingSkillLoader()
    router = KeywordSkillRouter(
        catalog=catalog,
        max_skills=2,
    )
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    builder = SkillContextBuilder(
        router=router,
        loader=loader,
        event_ledger=ledger,
    )

    context = await builder.build("pytest test failures documentation")

    assert loader.calls == [
        testing,
        documentation,
    ]
    assert context == SkillContext(
        skills=(
            LoadedSkill(
                manifest=testing,
                instructions=("Instructions for pytest-debugging."),
            ),
            LoadedSkill(
                manifest=documentation,
                instructions=("Instructions for docs."),
            ),
        ),
    )
    assert context.render() == (
        "# Loaded Skills\n"
        "\n"
        "## Skill: pytest-debugging\n"
        "\n"
        "Instructions for pytest-debugging.\n"
        "\n"
        "## Skill: docs\n"
        "\n"
        "Instructions for docs."
    )
    assert tuple(event.kind for event in ledger.events) == (
        EventKind.SKILL_SELECTION_FINISHED,
        EventKind.SKILL_LOAD_STARTED,
        EventKind.SKILL_LOAD_FINISHED,
        EventKind.SKILL_LOAD_STARTED,
        EventKind.SKILL_LOAD_FINISHED,
    )

    assert ledger.events[0].payload == {
        "selected": (
            {
                "skill_name": "pytest-debugging",
                "score": 3,
            },
            {
                "skill_name": "docs",
                "score": 1,
            },
        ),
    }

    assert ledger.events[2].payload == {
        "skill_name": "pytest-debugging",
        "outcome": "succeeded",
        "instruction_bytes": len(b"Instructions for pytest-debugging."),
    }


@pytest.mark.asyncio
async def test_skill_context_builder_handles_no_selection() -> None:
    catalog = SkillCatalog()
    catalog.register(
        SkillManifest(
            name="pytest-debugging",
            description=("Diagnose Python test failures."),
            entrypoint="SKILL.md",
        )
    )
    loader = RecordingSkillLoader()
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    builder = SkillContextBuilder(
        router=KeywordSkillRouter(
            catalog=catalog,
        ),
        loader=loader,
        event_ledger=ledger,
    )

    context = await builder.build("Translate release notes.")

    assert context.skills == ()
    assert context.render() == ""
    assert loader.calls == []
    assert tuple(event.kind for event in ledger.events) == (
        EventKind.SKILL_SELECTION_FINISHED,
    )

    assert ledger.events[0].payload == {
        "selected": (),
    }
