"""Validated metadata for one Coding Agent evaluation case."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

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


class TraceExpectations(BaseModel):
    """Preserve the schema-2 combined tool-use contract."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    required_successful_tools: tuple[str, ...]
    forbidden_tool_requests: tuple[str, ...]


class TraceExpectationsV3(BaseModel):
    """Separate diagnostic process coverage from trace safety."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    process_coverage_tools: tuple[str, ...]
    forbidden_tool_requests: tuple[str, ...]
    require_successful_test_after_change: bool


class EvaluationCaseManifest(BaseModel):
    """Preserve one schema-2 machine-readable case contract."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    schema_version: Literal[2]
    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ground_truth: GroundTruthSpec
    allowed_changes: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    trace_expectations: TraceExpectations
    budget: EvaluationBudget


class EvaluationCaseManifestV3(BaseModel):
    """Describe a case whose trace requirements have explicit semantics."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    schema_version: Literal[3]
    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ground_truth: GroundTruthSpec
    allowed_changes: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    trace_expectations: TraceExpectationsV3
    budget: EvaluationBudget


LoadedEvaluationCaseManifest = EvaluationCaseManifest | EvaluationCaseManifestV3


def load_case_manifest(
    case_root: Path,
) -> LoadedEvaluationCaseManifest:
    """Load and validate ``case.json`` from one case directory."""
    resolved_case_root = case_root.resolve(strict=True)
    manifest_json = (resolved_case_root / "case.json").read_text(encoding="utf-8")
    decoded: object = json.loads(manifest_json)

    if not isinstance(decoded, Mapping):
        raise TypeError("case manifest must be an object")

    schema_version = cast(Mapping[str, object], decoded).get("schema_version")

    if schema_version == 2:
        manifest: LoadedEvaluationCaseManifest = (
            EvaluationCaseManifest.model_validate_json(manifest_json)
        )
    elif schema_version == 3:
        manifest = EvaluationCaseManifestV3.model_validate_json(manifest_json)
    else:
        raise ValueError(f"unsupported case manifest schema: {schema_version}")

    if manifest.case_id != resolved_case_root.name:
        raise ValueError("case_id must match the case directory name")

    return manifest
