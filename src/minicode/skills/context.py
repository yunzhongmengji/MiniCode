"""Assembly of selected skills into model context."""

import asyncio
from collections.abc import (
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from typing import Protocol

from minicode.core.events import (
    EventKind,
    EventLedger,
)
from minicode.core.tool_calls import JsonValue
from minicode.skills.loader import (
    LoadedSkill,
    SkillLoader,
)
from minicode.skills.router import (
    SkillRouter,
)


@dataclass(frozen=True, slots=True)
class SkillContext:
    """Selected instructions for one model request."""

    skills: Sequence[LoadedSkill]

    def __post_init__(self) -> None:
        """Snapshot loaded skills."""
        object.__setattr__(
            self,
            "skills",
            tuple(self.skills),
        )

    def render(self) -> str:
        """Render loaded skills into deterministic text."""
        sections = tuple(
            (f"## Skill: {skill.manifest.name}\n\n{skill.instructions.strip()}")
            for skill in self.skills
        )

        if not sections:
            return ""

        return "# Loaded Skills\n\n" + "\n\n".join(sections)


class SkillContextProvider(Protocol):
    """Build selected skill context for one task."""

    async def build(
        self,
        query: str,
    ) -> SkillContext:
        """Return skill context for the task."""
        ...


class SkillContextBuilder:
    """Select and load skills for one task."""

    def __init__(
        self,
        *,
        router: SkillRouter,
        loader: SkillLoader,
        event_ledger: EventLedger | None = None,
    ) -> None:
        self._router = router
        self._loader = loader
        self._event_ledger = event_ledger

    def _record_event(
        self,
        kind: EventKind,
        payload: Mapping[str, JsonValue],
    ) -> None:
        """Record an event when configured."""
        if self._event_ledger is None:
            return

        self._event_ledger.record(
            kind,
            payload,
        )

    async def build(
        self,
        query: str,
    ) -> SkillContext:
        """Build context from selected skill instructions."""
        selected = self._router.select(query)

        self._record_event(
            EventKind.SKILL_SELECTION_FINISHED,
            {
                "selected": tuple(
                    {
                        "skill_name": (ranked_skill.manifest.name),
                        "score": ranked_skill.score,
                    }
                    for ranked_skill in selected
                ),
            },
        )

        loaded_skills: list[LoadedSkill] = []

        for rank, ranked_skill in enumerate(
            selected,
            start=1,
        ):
            manifest = ranked_skill.manifest

            self._record_event(
                EventKind.SKILL_LOAD_STARTED,
                {
                    "skill_name": manifest.name,
                    "rank": rank,
                    "score": ranked_skill.score,
                },
            )

            try:
                loaded = await self._loader.load(manifest)
            except asyncio.CancelledError:
                self._record_event(
                    EventKind.SKILL_LOAD_FINISHED,
                    {
                        "skill_name": manifest.name,
                        "outcome": "cancelled",
                    },
                )
                raise
            except Exception as error:
                self._record_event(
                    EventKind.SKILL_LOAD_FINISHED,
                    {
                        "skill_name": manifest.name,
                        "outcome": "failed",
                        "error_type": (type(error).__name__),
                    },
                )
                raise

            self._record_event(
                EventKind.SKILL_LOAD_FINISHED,
                {
                    "skill_name": manifest.name,
                    "outcome": "succeeded",
                    "instruction_bytes": len(loaded.instructions.encode("utf-8")),
                },
            )

            loaded_skills.append(loaded)

        return SkillContext(
            skills=loaded_skills,
        )
