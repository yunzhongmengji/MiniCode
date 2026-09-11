from pathlib import Path

import pytest

from minicode.evaluation_case import (
    EvaluationBudget,
    EvaluationCaseManifest,
    GroundTruthSpec,
    load_case_manifest,
)


def _cases_root() -> Path:
    return Path(__file__).resolve().parents[2] / "benchmarks" / "coding_agent" / "cases"


def test_loads_single_file_case_contract() -> None:
    case_root = _cases_root() / "single_file_batching"

    assert load_case_manifest(case_root) == EvaluationCaseManifest(
        schema_version=1,
        case_id="single_file_batching",
        category="single_file_repair",
        ground_truth=GroundTruthSpec(
            defined_by="project_maintainer",
            evidence=(
                "task.txt",
                "acceptance.py",
            ),
        ),
        allowed_changes=("batching.py",),
        forbidden_actions=(
            "modify tests",
            "create additional project files",
        ),
        budget=EvaluationBudget(
            max_turns=8,
            max_tool_calls=8,
        ),
    )


def test_every_committed_case_has_a_matching_manifest() -> None:
    case_roots = tuple(
        path for path in sorted(_cases_root().iterdir()) if path.is_dir()
    )

    assert tuple(load_case_manifest(path).case_id for path in case_roots) == tuple(
        path.name for path in case_roots
    )


def test_rejects_case_id_that_disagrees_with_directory(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "directory_name"
    case_root.mkdir()
    (case_root / "case.json").write_text(
        """{
  "schema_version": 1,
  "case_id": "different_name",
  "category": "fixture",
  "ground_truth": {
    "defined_by": "test",
    "evidence": ["acceptance.py"]
  },
  "allowed_changes": [],
  "forbidden_actions": [],
  "budget": {
    "max_turns": 1,
    "max_tool_calls": 1
  }
}
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="case_id must match the case directory name",
    ):
        load_case_manifest(case_root)
