from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.skills.retrieval import (
    KeywordSkillRanker,
    KeywordSkillRetriever,
    RankedSkill,
)


def test_keyword_retriever_recalls_matching_skills_in_catalog_order() -> None:
    documentation = SkillManifest(
        name="docs",
        description=("Write and maintain project documentation."),
        entrypoint="SKILL.md",
        tags=("writing",),
    )
    unrelated = SkillManifest(
        name="refactoring",
        description=("Restructure existing code."),
        entrypoint="SKILL.md",
        tags=("architecture",),
    )
    testing = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
        tags=("testing",),
    )
    security = SkillManifest(
        name="audit",
        description=("Inspect code for vulnerabilities."),
        entrypoint="SKILL.md",
        tags=("security",),
    )
    retriever = KeywordSkillRetriever()

    candidates = retriever.recall(
        query=("Fix PYTEST, update documentation, and perform a SECURITY review."),
        manifests=(
            documentation,
            unrelated,
            testing,
            security,
        ),
    )

    assert candidates == (
        documentation,
        testing,
        security,
    )


def test_keyword_retriever_returns_empty_tuple_without_matches() -> None:
    manifest = SkillManifest(
        name="pytest-debugging",
        description=("Diagnose Python test failures."),
        entrypoint="SKILL.md",
        tags=("testing",),
    )
    retriever = KeywordSkillRetriever()

    candidates = retriever.recall(
        query="Translate release notes.",
        manifests=(manifest,),
    )

    assert candidates == ()


def test_keyword_ranker_orders_candidates_by_shared_words() -> None:
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
    query = "pytest test failures documentation"
    retriever = KeywordSkillRetriever()
    ranker = KeywordSkillRanker()

    candidates = retriever.recall(
        query=query,
        manifests=(
            documentation,
            testing,
        ),
    )
    ranked = ranker.rank(
        query=query,
        candidates=candidates,
    )

    assert ranked == (
        RankedSkill(
            manifest=testing,
            score=3,
        ),
        RankedSkill(
            manifest=documentation,
            score=1,
        ),
    )


def test_keyword_ranker_preserves_candidate_order_for_ties() -> None:
    first = SkillManifest(
        name="python-testing",
        description="Run test suites.",
        entrypoint="SKILL.md",
    )
    second = SkillManifest(
        name="python-review",
        description="Review source code.",
        entrypoint="SKILL.md",
    )
    ranker = KeywordSkillRanker()

    ranked = ranker.rank(
        query="python",
        candidates=(
            first,
            second,
        ),
    )

    assert ranked == (
        RankedSkill(
            manifest=first,
            score=1,
        ),
        RankedSkill(
            manifest=second,
            score=1,
        ),
    )
