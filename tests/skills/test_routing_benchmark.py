"""Validate and evaluate the fixed synthetic Skill-routing dataset."""

import json
from pathlib import Path

from minicode.skills.catalog import SkillCatalog
from minicode.skills.evaluation import SkillRoutingCase, evaluate_skill_router
from minicode.skills.manifest import SkillManifest
from minicode.skills.router import KeywordSkillRouter

_DATASET_PATH = Path(__file__).resolve().parents[2] / "benchmarks/skill_routing/v1.json"


def test_routing_v1_dataset_has_consistent_labels_and_configuration() -> None:
    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))

    assert dataset["schema_version"] == 1
    assert dataset["dataset_version"] == "skill-routing-v1"
    assert dataset["label_source"] == "synthetic draft; pending owner review"
    assert dataset["router"] == {"name": "KeywordSkillRouter", "max_skills": 3}
    names = [manifest["name"] for manifest in dataset["catalog"]]
    assert len(names) == len(set(names)) == 4
    cases = dataset["cases"]
    assert len(cases) == 12
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["category"] for case in cases} == {
        "positive",
        "negative",
        "similar",
        "tie",
        "synonym",
        "cross-language",
        "multiple",
    }
    for case in cases:
        assert case["id"].strip()
        assert case["query"].strip()
        assert case["rationale"].strip()
        expected = case["expected_skill_names"]
        assert len(expected) == len(set(expected))
        assert len(expected) <= dataset["router"]["max_skills"]
        assert set(expected) <= set(names)


def test_routing_v1_dataset_runs_reproducibly_with_metadata_only() -> None:
    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    catalog = SkillCatalog()
    for manifest in dataset["catalog"]:
        catalog.register(SkillManifest(**manifest))
    router = KeywordSkillRouter(
        catalog=catalog,
        max_skills=dataset["router"]["max_skills"],
    )
    cases = tuple(
        SkillRoutingCase(
            query=case["query"],
            expected_skill_names=case["expected_skill_names"],
        )
        for case in dataset["cases"]
    )

    report = evaluate_skill_router(router=router, cases=cases)
    repeated = evaluate_skill_router(router=router, cases=cases)

    assert report.total_cases == len(cases)
    assert report.results == repeated.results
    assert tuple(result.case for result in report.results) == cases
    for result in report.results:
        assert len(result.selected_skill_names) <= dataset["router"]["max_skills"]
        assert len(result.selected_skill_names) == len(set(result.selected_skill_names))
        assert set(result.selected_skill_names) <= {m.name for m in catalog.manifests}
