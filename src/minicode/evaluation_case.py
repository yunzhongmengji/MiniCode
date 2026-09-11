"""Validated metadata for one Coding Agent evaluation case."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GroundTruthSpec(BaseModel):
    """Describe who defined correctness and where it is enforced."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    defined_by: str = Field(min_length=1)
    evidence: tuple[str, ...] = Field(min_length=1)


class EvaluationBudget(BaseModel):
    """Bound model turns and tool executions for one case."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    max_turns: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)


class EvaluationCaseManifest(BaseModel):
    """Machine-readable contract for one evaluation case."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    schema_version: int = Field(ge=1)
    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ground_truth: GroundTruthSpec
    allowed_changes: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    budget: EvaluationBudget


def load_case_manifest(
    case_root: Path,
) -> EvaluationCaseManifest:
    """Load and validate ``case.json`` from one case directory."""
    resolved_case_root = case_root.resolve(strict=True)
    manifest = EvaluationCaseManifest.model_validate_json(
        (resolved_case_root / "case.json").read_text(
            encoding="utf-8",
        )
    )

    if manifest.case_id != resolved_case_root.name:
        raise ValueError("case_id must match the case directory name")

    return manifest
