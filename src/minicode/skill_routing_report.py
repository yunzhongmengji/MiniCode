"""Generate an offline report from a versioned Skill-routing dataset."""

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from minicode.skills.catalog import SkillCatalog
from minicode.skills.evaluation import SkillRoutingCase, evaluate_skill_router
from minicode.skills.manifest import SkillManifest
from minicode.skills.router import KeywordSkillRouter


def _text(value: object, field: str) -> str:
    """Require a nonblank dataset string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value


def build_skill_routing_report(dataset_path: Path) -> dict[str, object]:
    """Validate metadata, run the existing router, and describe every case."""
    raw = dataset_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise TypeError("dataset must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("dataset schema_version must be 1")
    version = _text(data.get("dataset_version"), "dataset_version")
    label_source = _text(data.get("label_source"), "label_source")
    configuration = data.get("router")
    if (
        not isinstance(configuration, dict)
        or configuration.get("name") != "KeywordSkillRouter"
    ):
        raise ValueError("router.name must be KeywordSkillRouter")
    if set(configuration) != {"name", "max_skills"}:
        raise ValueError("router must contain only name and max_skills")
    max_skills = configuration.get("max_skills")
    if type(max_skills) is not int:
        raise TypeError("router.max_skills must be an integer")
    manifests = data.get("catalog")
    if not isinstance(manifests, list) or not manifests:
        raise ValueError("catalog must be a nonempty array")
    catalog = SkillCatalog()
    for manifest in manifests:
        if not isinstance(manifest, dict):
            raise TypeError("catalog entries must be objects")
        catalog.register(SkillManifest(**manifest))
    router = KeywordSkillRouter(
        catalog=catalog,
        max_skills=max_skills,
    )
    samples = data.get("cases")
    if not isinstance(samples, list) or not samples:
        raise ValueError("cases must be a nonempty array")
    cases: list[SkillRoutingCase] = []
    identifiers: set[str] = set()
    catalog_names = {manifest.name for manifest in catalog.manifests}
    for sample in samples:
        if not isinstance(sample, dict):
            raise TypeError("cases entries must be objects")
        case_id = _text(sample.get("id"), "case.id")
        if case_id in identifiers:
            raise ValueError(f"duplicate case id: {case_id}")
        identifiers.add(case_id)
        _text(sample.get("category"), f"{case_id}.category")
        _text(sample.get("rationale"), f"{case_id}.rationale")
        query = _text(sample.get("query"), f"{case_id}.query")
        names = sample.get("expected_skill_names")
        if not isinstance(names, list):
            raise TypeError(f"{case_id}.expected_skill_names must be an array")
        expected = tuple(
            _text(name, f"{case_id}.expected_skill_names") for name in names
        )
        if len(expected) != len(set(expected)):
            raise ValueError(f"{case_id}: expected Skill names must be unique")
        if set(expected) - catalog_names:
            raise ValueError(f"{case_id}: expected Skill names must exist in catalog")
        if len(expected) > max_skills:
            raise ValueError(f"{case_id}: expected selection exceeds max_skills")
        cases.append(SkillRoutingCase(query=query, expected_skill_names=expected))

    report = evaluate_skill_router(router=router, cases=cases)
    results: list[dict[str, object]] = []
    failed_case_ids: list[str] = []
    for sample, result in zip(samples, report.results, strict=True):
        if not result.exact_match:
            failed_case_ids.append(sample["id"])
        results.append(
            {
                "id": sample["id"],
                "category": sample["category"],
                "query": result.case.query,
                "rationale": sample["rationale"],
                "expected_skill_names": list(result.case.expected_skill_names),
                "selected_skill_names": list(result.selected_skill_names),
                "missing_skill_names": list(result.missing_skill_names),
                "unexpected_skill_names": list(result.unexpected_skill_names),
                "exact_match": result.exact_match,
            }
        )
    return {
        "schema_version": 1,
        "dataset_version": version,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "label_source": label_source,
        "router": {
            "name": "KeywordSkillRouter",
            "max_skills": max_skills,
        },
        "catalog": manifests,
        "summary": {
            "total_cases": report.total_cases,
            "exact_matches": report.exact_matches,
            "exact_match_ratio": report.accuracy,
            "missing_cases": sum(
                bool(result.missing_skill_names) for result in report.results
            ),
            "unexpected_cases": sum(
                bool(result.unexpected_skill_names) for result in report.results
            ),
            "failed_case_ids": failed_case_ids,
        },
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Print a JSON report; case mismatches are data, not execution errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset", type=Path, help="Path to a schema-1 routing dataset."
    )
    args = parser.parse_args(argv)
    try:
        report = build_skill_routing_report(args.dataset)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        print(f"Routing report error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
