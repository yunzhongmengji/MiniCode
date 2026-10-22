import pytest

from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.evaluation import (
    SkillRoutingCase,
    SkillRoutingReport,
    SkillRoutingResult,
    evaluate_skill_router,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.skills.router import (
    KeywordSkillRouter,
)


def test_keyword_skill_router_meets_routing_benchmark() -> None:
    catalog = SkillCatalog()

    catalog.register(
        SkillManifest(
            name="documentation",
            description=("Write and maintain project documentation."),
            entrypoint="SKILL.md",
            tags=(
                "writing",
                "documentation",
            ),
        )
    )
    catalog.register(
        SkillManifest(
            name="pytest-debugging",
            description=("Diagnose Python pytest test failures."),
            entrypoint="SKILL.md",
            tags=(
                "pytest",
                "testing",
            ),
        )
    )
    catalog.register(
        SkillManifest(
            name="security-audit",
            description=("Inspect code for security vulnerabilities."),
            entrypoint="SKILL.md",
            tags=(
                "security",
                "audit",
            ),
        )
    )

    router = KeywordSkillRouter(
        catalog=catalog,
        max_skills=1,
    )
    cases = (
        SkillRoutingCase(
            query=("Fix the failing pytest test."),
            expected_skill_names=("pytest-debugging",),
        ),
        SkillRoutingCase(
            query=("Update the project documentation."),
            expected_skill_names=("documentation",),
        ),
        SkillRoutingCase(
            query=("Audit this code for security vulnerabilities."),
            expected_skill_names=("security-audit",),
        ),
        SkillRoutingCase(
            query=("What is the weather today?"),
            expected_skill_names=(),
        ),
    )

    report = evaluate_skill_router(
        router=router,
        cases=cases,
    )

    assert report.total_cases == 4
    assert report.exact_matches == 4
    assert report.accuracy == 1.0

    assert tuple(result.selected_skill_names for result in report.results) == (
        ("pytest-debugging",),
        ("documentation",),
        ("security-audit",),
        (),
    )
    assert report.failures == ()
    assert report.passed is True
    assert all(result.missing_skill_names == () for result in report.results)
    assert all(result.unexpected_skill_names == () for result in report.results)


def test_routing_report_exposes_failed_cases() -> None:
    case = SkillRoutingCase(
        query="Fix the failing pytest test.",
        expected_skill_names=("pytest-debugging",),
    )
    failed_result = SkillRoutingResult(
        case=case,
        selected_skill_names=("documentation",),
    )

    report = SkillRoutingReport(
        results=(failed_result,),
    )

    assert report.total_cases == 1
    assert report.exact_matches == 0
    assert report.accuracy == 0.0
    assert report.failures == (failed_result,)
    assert report.passed is False
    assert report.failures[0].missing_skill_names == ("pytest-debugging",)
    assert report.failures[0].unexpected_skill_names == ("documentation",)


@pytest.mark.parametrize(
    ("expected", "selected", "missing", "unexpected", "exact_match"),
    (
        (("documentation",), ("documentation",), (), (), True),
        (("documentation",), (), ("documentation",), (), False),
        ((), ("documentation",), (), ("documentation",), False),
        (
            ("pytest-debugging",),
            ("documentation",),
            ("pytest-debugging",),
            ("documentation",),
            False,
        ),
        ((), (), (), (), True),
        (
            ("documentation", "pytest-debugging"),
            ("pytest-debugging", "documentation"),
            (),
            (),
            False,
        ),
        (
            ("security-audit", "pytest-debugging", "documentation"),
            ("documentation", "z-extra", "a-extra"),
            ("security-audit", "pytest-debugging"),
            ("z-extra", "a-extra"),
            False,
        ),
    ),
    ids=("matched", "missing", "unexpected", "wrong", "empty", "order-only", "mixed"),
)
def test_routing_result_identifies_missing_and_unexpected_skills(
    expected: tuple[str, ...],
    selected: tuple[str, ...],
    missing: tuple[str, ...],
    unexpected: tuple[str, ...],
    exact_match: bool,
) -> None:
    result = SkillRoutingResult(
        case=SkillRoutingCase(query="Example task.", expected_skill_names=expected),
        selected_skill_names=selected,
    )

    assert result.missing_skill_names == missing
    assert result.unexpected_skill_names == unexpected
    assert result.exact_match is exact_match
    assert tuple(result.case.expected_skill_names) == expected
    assert tuple(result.selected_skill_names) == selected
