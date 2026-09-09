"""Evaluation of skill-routing behavior."""

from collections.abc import Sequence
from dataclasses import dataclass

from minicode.skills.router import (
    SkillRouter,
)


@dataclass(frozen=True, slots=True)
class SkillRoutingCase:
    """One routing query and its expected selection."""

    query: str
    expected_skill_names: Sequence[str]

    def __post_init__(self) -> None:
        """Snapshot the expected skill names."""
        object.__setattr__(
            self,
            "expected_skill_names",
            tuple(self.expected_skill_names),
        )


@dataclass(frozen=True, slots=True)
class SkillRoutingResult:
    """Observed result for one routing case."""

    case: SkillRoutingCase
    selected_skill_names: Sequence[str]

    def __post_init__(self) -> None:
        """Snapshot selected skill names."""
        object.__setattr__(
            self,
            "selected_skill_names",
            tuple(self.selected_skill_names),
        )

    @property
    def exact_match(self) -> bool:
        """Return whether selection exactly matches expectation."""
        return self.selected_skill_names == self.case.expected_skill_names


@dataclass(frozen=True, slots=True)
class SkillRoutingReport:
    """Summary of multiple routing cases."""

    results: Sequence[SkillRoutingResult]

    def __post_init__(self) -> None:
        """Snapshot routing results."""
        object.__setattr__(
            self,
            "results",
            tuple(self.results),
        )

    @property
    def total_cases(self) -> int:
        """Return the number of evaluated cases."""
        return len(self.results)

    @property
    def exact_matches(self) -> int:
        """Return the number of exact matches."""
        return sum(result.exact_match for result in self.results)

    @property
    def failures(
        self,
    ) -> tuple[SkillRoutingResult, ...]:
        """Return cases that did not exactly match."""
        return tuple(result for result in self.results if not result.exact_match)

    @property
    def passed(self) -> bool:
        """Return whether every routing case matched."""
        return not self.failures

    @property
    def accuracy(self) -> float:
        """Return the exact-match ratio."""
        if self.total_cases == 0:
            return 0.0

        return self.exact_matches / self.total_cases


def evaluate_skill_router(
    *,
    router: SkillRouter,
    cases: Sequence[SkillRoutingCase],
) -> SkillRoutingReport:
    """Evaluate a router against labeled cases."""
    results: list[SkillRoutingResult] = []

    for case in cases:
        selected = router.select(case.query)
        selected_names = tuple(ranked_skill.manifest.name for ranked_skill in selected)

        results.append(
            SkillRoutingResult(
                case=case,
                selected_skill_names=(selected_names),
            )
        )

    return SkillRoutingReport(
        results=results,
    )
