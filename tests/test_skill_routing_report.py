"""Exercise the offline routing report and its command boundary."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from minicode.skill_routing_report import build_skill_routing_report, main

_DATASET_PATH = Path(__file__).resolve().parents[1] / "benchmarks/skill_routing/v1.json"


def test_report_preserves_configuration_and_all_case_diagnostics() -> None:
    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    report = build_skill_routing_report(_DATASET_PATH)
    assert report == build_skill_routing_report(_DATASET_PATH)
    assert report["schema_version"] == 1
    assert report["dataset_version"] == dataset["dataset_version"]
    assert report["label_source"] == dataset["label_source"]
    assert (
        report["dataset_sha256"]
        == hashlib.sha256(_DATASET_PATH.read_bytes()).hexdigest()
    )
    assert report["router"] == dataset["router"]
    assert report["catalog"] == dataset["catalog"]
    results = report["results"]
    assert isinstance(results, list)
    assert len(results) == len(dataset["cases"])
    for sample, result in zip(dataset["cases"], results, strict=True):
        assert result["id"] == sample["id"]
        assert result["query"] == sample["query"]
        assert result["category"] == sample["category"]
        assert result["rationale"] == sample["rationale"]
        assert result["expected_skill_names"] == sample["expected_skill_names"]
        assert result["missing_skill_names"] == [
            name
            for name in sample["expected_skill_names"]
            if name not in result["selected_skill_names"]
        ]
        assert result["unexpected_skill_names"] == [
            name
            for name in result["selected_skill_names"]
            if name not in sample["expected_skill_names"]
        ]
        assert result["exact_match"] == (
            result["selected_skill_names"] == sample["expected_skill_names"]
        )
    assert report["summary"] == {
        "total_cases": len(results),
        "exact_matches": sum(result["exact_match"] for result in results),
        "exact_match_ratio": sum(result["exact_match"] for result in results)
        / len(results),
        "missing_cases": sum(bool(result["missing_skill_names"]) for result in results),
        "unexpected_cases": sum(
            bool(result["unexpected_skill_names"]) for result in results
        ),
        "failed_case_ids": [
            result["id"] for result in results if not result["exact_match"]
        ],
    }


def test_report_command_returns_zero_even_when_a_case_does_not_match(
    tmp_path, capsys
) -> None:
    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    dataset["cases"] = [
        {
            "id": "deliberate-mismatch",
            "category": "fixture",
            "query": "pytest",
            "expected_skill_names": [],
            "rationale": "Deliberate mismatch for exit-code testing.",
        }
    ]
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    assert main([str(path)]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report["summary"]["failed_case_ids"] == ["deliberate-mismatch"]
    assert report["results"][0]["unexpected_skill_names"] == ["pytest-debugging"]


@pytest.mark.parametrize(
    "problem",
    (
        "schema",
        "router",
        "unknown-parameter",
        "limit",
        "duplicate-id",
        "unknown-skill",
        "duplicate-skill",
        "empty-cases",
    ),
)
def test_report_command_rejects_invalid_dataset(problem, tmp_path, capsys) -> None:
    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    if problem == "schema":
        dataset["schema_version"] = True
    elif problem == "router":
        dataset["router"]["name"] = "UnsupportedRouter"
    elif problem == "unknown-parameter":
        dataset["router"]["minimum_score"] = 2
    elif problem == "limit":
        dataset["router"]["max_skills"] = True
    elif problem == "duplicate-id":
        dataset["cases"][1]["id"] = dataset["cases"][0]["id"]
    elif problem == "unknown-skill":
        dataset["cases"][0]["expected_skill_names"] = ["unknown"]
    elif problem == "duplicate-skill":
        dataset["cases"][0]["expected_skill_names"] = ["documentation", "documentation"]
    else:
        dataset["cases"] = []
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    assert main([str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Routing report error:" in captured.err


@pytest.mark.parametrize("exists", (True, False), ids=("invalid-json", "missing-file"))
def test_report_command_reports_unreadable_dataset(exists, tmp_path, capsys) -> None:
    path = tmp_path / "dataset.json"
    if exists:
        path.write_text("{not JSON", encoding="utf-8")
    assert main([str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Routing report error:" in captured.err


def test_report_module_command_works_outside_repository_directory(tmp_path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "minicode.skill_routing_report", str(_DATASET_PATH)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    report = json.loads(completed.stdout)
    assert report["dataset_version"] == "skill-routing-v1"
    assert len(report["results"]) == 12
