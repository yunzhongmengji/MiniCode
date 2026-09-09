"""Candidate retrieval for skill selection."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from minicode.skills.manifest import (
    SkillManifest,
)

_TOKEN_SEPARATOR = re.compile(r"[\W_]+")


def _tokenize(
    text: str,
) -> frozenset[str]:
    """Normalize text into unique searchable tokens."""
    normalized_text = text.casefold()

    return frozenset(
        token for token in _TOKEN_SEPARATOR.split(normalized_text) if token
    )


def _manifest_tokens(
    manifest: SkillManifest,
) -> frozenset[str]:
    """Collect searchable tokens from one manifest."""
    metadata = (
        manifest.name,
        manifest.description,
        *manifest.tags,
    )
    tokens: set[str] = set()

    for value in metadata:
        tokens.update(_tokenize(value))

    return frozenset(tokens)


@dataclass(frozen=True, slots=True)
class RankedSkill:
    """One recalled skill with its relevance score."""

    manifest: SkillManifest
    score: int


class KeywordSkillRetriever:
    """Recall skill candidates using metadata words."""

    def recall(
        self,
        *,
        query: str,
        manifests: Sequence[SkillManifest],
    ) -> tuple[SkillManifest, ...]:
        """Return manifests sharing words with a task."""
        query_tokens = _tokenize(query)

        return tuple(
            manifest
            for manifest in manifests
            if query_tokens & _manifest_tokens(manifest)
        )


class KeywordSkillRanker:
    """Rank recalled skills by shared metadata words."""

    def rank(
        self,
        *,
        query: str,
        candidates: Sequence[SkillManifest],
    ) -> tuple[RankedSkill, ...]:
        """Order candidates by descending relevance."""
        query_tokens = _tokenize(query)
        ranked = tuple(
            RankedSkill(
                manifest=manifest,
                score=len(query_tokens & _manifest_tokens(manifest)),
            )
            for manifest in candidates
        )

        return tuple(
            sorted(
                ranked,
                key=lambda item: -item.score,
            )
        )
