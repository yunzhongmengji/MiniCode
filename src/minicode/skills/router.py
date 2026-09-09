"""Skill routing from tasks to ranked manifests."""

from typing import Protocol

from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.retrieval import (
    KeywordSkillRanker,
    KeywordSkillRetriever,
    RankedSkill,
)


class SkillRouter(Protocol):
    """Select ranked skills for one task."""

    def select(
        self,
        query: str,
    ) -> tuple[RankedSkill, ...]:
        """Return selected skills in relevance order."""
        ...


class KeywordSkillRouter:
    """Select relevant skills using keyword matching."""

    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        max_skills: int = 3,
    ) -> None:
        if type(max_skills) is not int:
            raise TypeError("max_skills must be an integer")

        if max_skills <= 0:
            raise ValueError("max_skills must be greater than zero")

        self._catalog = catalog
        self._max_skills = max_skills
        self._retriever = KeywordSkillRetriever()
        self._ranker = KeywordSkillRanker()

    def select(
        self,
        query: str,
    ) -> tuple[RankedSkill, ...]:
        """Select the highest-ranked matching skills."""
        candidates = self._retriever.recall(
            query=query,
            manifests=self._catalog.manifests,
        )
        ranked = self._ranker.rank(
            query=query,
            candidates=candidates,
        )

        return ranked[: self._max_skills]
