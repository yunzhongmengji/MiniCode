from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.skills.retrieval import (
    RankedSkill,
)
from minicode.skills.router import (
    KeywordSkillRouter,
)


def test_keyword_skill_router_selects_highest_ranked_skills() -> None:
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
    security = SkillManifest(
        name="security-review",
        description=("Review code security."),
        entrypoint="SKILL.md",
    )
    catalog = SkillCatalog()
    catalog.register(documentation)
    catalog.register(testing)
    catalog.register(security)

    router = KeywordSkillRouter(
        catalog=catalog,
        max_skills=2,
    )

    selected = router.select("pytest test failures documentation security")

    assert selected == (
        RankedSkill(
            manifest=testing,
            score=3,
        ),
        RankedSkill(
            manifest=documentation,
            score=1,
        ),
    )
