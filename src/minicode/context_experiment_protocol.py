"""Load pre-registered protocols for budgeted context experiments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
    ContextProjectionConfiguration,
    ContextProjectionStrategy,
)


@dataclass(frozen=True, slots=True)
class ContextExperimentModel:
    """The provider settings frozen before an experiment starts."""

    provider: str
    name: str
    enable_thinking: bool
    temperature_control: str


@dataclass(frozen=True, slots=True)
class ContextExperimentBudget:
    """Run count and post-run Provider-token gates for one experiment phase."""

    maximum_runs: int
    maximum_input_tokens: int
    maximum_output_tokens: int


@dataclass(frozen=True, slots=True)
class BudgetedContextPreflightPlan:
    """The small paired run that must pass before the formal experiment."""

    case_id: str
    arm_order: tuple[str, ...]
    required_safe_successes_per_arm: int
    minimum_changed_tool_result_count: int
    maximum_failed_or_cancelled_readbacks: int
    provider_usage_required: bool
    complete_artifact_set_required: bool
    budget: ContextExperimentBudget


@dataclass(frozen=True, slots=True)
class ContextExperimentAdvancementGates:
    """The result thresholds frozen before formal runs start."""

    required_safe_task_successes_per_arm: int
    minimum_aggregate_input_token_reduction_percent: int
    maximum_per_case_input_token_regression_percent: int
    maximum_forbidden_side_effects: int
    maximum_failed_or_cancelled_readbacks: int


@dataclass(frozen=True, slots=True)
class BudgetedContextExperimentProtocol:
    """One complete schema-3 context experiment registration."""

    protocol_id: str
    status: str
    model: ContextExperimentModel
    cases: tuple[str, ...]
    baseline_configuration: ContextProjectionConfiguration
    projection_configuration: BudgetedContextProjectionConfiguration
    preflight_plan: BudgetedContextPreflightPlan
    repetitions_per_case_per_arm: int
    paired_arm_order_per_case: tuple[str, ...]
    implementation_version_rule: str
    formal_budget: ContextExperimentBudget
    advancement_gates: ContextExperimentAdvancementGates


def load_budgeted_context_experiment_protocol(
    path: Path,
) -> BudgetedContextExperimentProtocol:
    """Load and cross-check one pre-registered schema-3 protocol."""
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"budgeted context protocol must be an object: {path}")

    protocol = cast(Mapping[str, object], decoded)
    _require_exact_fields(
        protocol,
        {
            "schema_version",
            "protocol_id",
            "status",
            "model",
            "cases",
            "arms",
            "preflight_plan",
            "repetitions_per_case_per_arm",
            "paired_arm_order_per_case",
            "implementation_version_rule",
            "preflight_budget",
            "formal_budget",
            "advancement_gates",
        },
        "budgeted context protocol",
        path,
    )

    if _required_integer(protocol, "schema_version", path) != 3:
        raise ValueError(f"unsupported budgeted context protocol schema: {path}")

    status = _required_non_blank_string(protocol, "status", path)

    if status != "pre_registered_preflight_not_run":
        raise ValueError(f"budgeted context protocol status is not pre-registered: {path}")

    model = _load_model(_required_mapping(protocol, "model", path), path)
    cases = _required_string_tuple(protocol, "cases", path)

    if not cases:
        raise ValueError(f"budgeted context protocol cases must not be empty: {path}")

    if len(set(cases)) != len(cases):
        raise ValueError(f"budgeted context protocol case IDs must be unique: {path}")

    arms = _required_mapping(protocol, "arms", path)
    _require_exact_fields(arms, {"baseline", "projection"}, "arms", path)
    baseline = _load_identity_configuration(
        _required_mapping(arms, "baseline", path),
        path,
    )
    projection_payload = _required_mapping(arms, "projection", path)
    projection = BudgetedContextProjectionConfiguration.from_payload(
        projection_payload
    )
    preflight_budget = _load_budget(
        _required_mapping(protocol, "preflight_budget", path),
        path,
        "preflight_budget",
    )
    preflight = _load_preflight_plan(
        _required_mapping(protocol, "preflight_plan", path),
        preflight_budget,
        cases,
        path,
    )
    repetitions = _required_positive_integer(
        protocol,
        "repetitions_per_case_per_arm",
        path,
    )
    paired_order = _required_string_tuple(
        protocol,
        "paired_arm_order_per_case",
        path,
    )
    _validate_paired_order(paired_order, repetitions, path)
    formal_budget = _load_budget(
        _required_mapping(protocol, "formal_budget", path),
        path,
        "formal_budget",
    )
    expected_formal_runs = len(cases) * repetitions * 2

    if formal_budget.maximum_runs != expected_formal_runs:
        raise ValueError(
            "formal maximum_runs must equal cases times repetitions times arms: "
            f"{path}"
        )

    gates = _load_advancement_gates(
        _required_mapping(protocol, "advancement_gates", path),
        path,
    )
    expected_safe_successes = len(cases) * repetitions

    if gates.required_safe_task_successes_per_arm != expected_safe_successes:
        raise ValueError(
            "required safe successes must equal cases times repetitions: "
            f"{path}"
        )

    return BudgetedContextExperimentProtocol(
        protocol_id=_required_non_blank_string(protocol, "protocol_id", path),
        status=status,
        model=model,
        cases=cases,
        baseline_configuration=baseline,
        projection_configuration=projection,
        preflight_plan=preflight,
        repetitions_per_case_per_arm=repetitions,
        paired_arm_order_per_case=paired_order,
        implementation_version_rule=_required_non_blank_string(
            protocol,
            "implementation_version_rule",
            path,
        ),
        formal_budget=formal_budget,
        advancement_gates=gates,
    )


def _load_model(
    source: Mapping[str, object],
    path: Path,
) -> ContextExperimentModel:
    _require_exact_fields(
        source,
        {"provider", "name", "enable_thinking", "temperature_control"},
        "model",
        path,
    )
    return ContextExperimentModel(
        provider=_required_non_blank_string(source, "provider", path),
        name=_required_non_blank_string(source, "name", path),
        enable_thinking=_required_boolean(source, "enable_thinking", path),
        temperature_control=_required_non_blank_string(
            source,
            "temperature_control",
            path,
        ),
    )


def _load_identity_configuration(
    source: Mapping[str, object],
    path: Path,
) -> ContextProjectionConfiguration:
    expected = ContextProjectionConfiguration(
        strategy=ContextProjectionStrategy.IDENTITY,
        max_inline_tool_result_bytes=None,
        minimum_net_savings_bytes=None,
        retrieval_tool_loading=None,
    )

    if dict(source) != expected.to_payload():
        raise ValueError(f"baseline must be the complete schema-2 identity arm: {path}")

    return expected


def _load_budget(
    source: Mapping[str, object],
    path: Path,
    field_name: str,
) -> ContextExperimentBudget:
    _require_exact_fields(
        source,
        {"maximum_runs", "maximum_input_tokens", "maximum_output_tokens"},
        field_name,
        path,
    )
    return ContextExperimentBudget(
        maximum_runs=_required_positive_integer(source, "maximum_runs", path),
        maximum_input_tokens=_required_positive_integer(
            source,
            "maximum_input_tokens",
            path,
        ),
        maximum_output_tokens=_required_positive_integer(
            source,
            "maximum_output_tokens",
            path,
        ),
    )


def _load_preflight_plan(
    source: Mapping[str, object],
    budget: ContextExperimentBudget,
    cases: tuple[str, ...],
    path: Path,
) -> BudgetedContextPreflightPlan:
    _require_exact_fields(
        source,
        {"case", "arm_order", "runs", "success_requirements"},
        "preflight_plan",
        path,
    )
    case_id = _required_non_blank_string(source, "case", path)

    if case_id not in cases:
        raise ValueError(f"preflight case must be a protocol case: {path}")

    arm_order = _required_string_tuple(source, "arm_order", path)

    if sorted(arm_order) != ["baseline", "projection"]:
        raise ValueError(
            f"preflight must contain baseline and projection exactly once: {path}"
        )

    runs = _required_positive_integer(source, "runs", path)

    if runs != len(arm_order) or budget.maximum_runs != runs:
        raise ValueError(
            f"preflight run count must match arm order and budget: {path}"
        )

    requirements = _required_mapping(source, "success_requirements", path)
    _require_exact_fields(
        requirements,
        {
            "safe_task_successes_per_arm",
            "minimum_changed_tool_result_count",
            "maximum_failed_or_cancelled_readbacks",
            "provider_usage_required",
            "complete_artifact_set_required",
        },
        "preflight success_requirements",
        path,
    )
    safe_successes = _required_positive_integer(
        requirements,
        "safe_task_successes_per_arm",
        path,
    )

    if safe_successes != 1:
        raise ValueError(f"preflight requires one safe success per arm: {path}")

    return BudgetedContextPreflightPlan(
        case_id=case_id,
        arm_order=arm_order,
        required_safe_successes_per_arm=safe_successes,
        minimum_changed_tool_result_count=_required_positive_integer(
            requirements,
            "minimum_changed_tool_result_count",
            path,
        ),
        maximum_failed_or_cancelled_readbacks=_required_non_negative_integer(
            requirements,
            "maximum_failed_or_cancelled_readbacks",
            path,
        ),
        provider_usage_required=_required_boolean(
            requirements,
            "provider_usage_required",
            path,
        ),
        complete_artifact_set_required=_required_boolean(
            requirements,
            "complete_artifact_set_required",
            path,
        ),
        budget=budget,
    )


def _load_advancement_gates(
    source: Mapping[str, object],
    path: Path,
) -> ContextExperimentAdvancementGates:
    _require_exact_fields(
        source,
        {
            "required_safe_task_successes_per_arm",
            "minimum_aggregate_input_token_reduction_percent",
            "maximum_per_case_input_token_regression_percent",
            "maximum_forbidden_side_effects",
            "maximum_failed_or_cancelled_readbacks",
        },
        "advancement_gates",
        path,
    )
    return ContextExperimentAdvancementGates(
        required_safe_task_successes_per_arm=_required_non_negative_integer(
            source,
            "required_safe_task_successes_per_arm",
            path,
        ),
        minimum_aggregate_input_token_reduction_percent=(
            _required_non_negative_integer(
                source,
                "minimum_aggregate_input_token_reduction_percent",
                path,
            )
        ),
        maximum_per_case_input_token_regression_percent=(
            _required_non_negative_integer(
                source,
                "maximum_per_case_input_token_regression_percent",
                path,
            )
        ),
        maximum_forbidden_side_effects=_required_non_negative_integer(
            source,
            "maximum_forbidden_side_effects",
            path,
        ),
        maximum_failed_or_cancelled_readbacks=_required_non_negative_integer(
            source,
            "maximum_failed_or_cancelled_readbacks",
            path,
        ),
    )


def _validate_paired_order(
    arm_order: tuple[str, ...],
    repetitions: int,
    path: Path,
) -> None:
    if len(arm_order) != repetitions * 2:
        raise ValueError(
            f"paired arm order must contain two entries per repetition: {path}"
        )

    for arm in arm_order:
        if arm not in ("baseline", "projection"):
            raise ValueError(f"paired arm order contains unknown arm: {path}")

    if arm_order.count("baseline") != repetitions or arm_order.count(
        "projection"
    ) != repetitions:
        raise ValueError(
            f"paired arm order must balance baseline and projection: {path}"
        )


def _require_exact_fields(
    source: Mapping[str, object],
    expected: set[str],
    object_name: str,
    path: Path,
) -> None:
    actual = set(source)

    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"{object_name} fields do not match schema: "
            f"missing={missing}, unexpected={unexpected}: {path}"
        )


def _required_mapping(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> Mapping[str, object]:
    value = source.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object: {path}")

    return cast(Mapping[str, object], value)


def _required_non_blank_string(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> str:
    value = source.get(key)

    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string: {path}")

    if not value.strip():
        raise ValueError(f"{key} must not be blank: {path}")

    return value


def _required_string_tuple(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> tuple[str, ...]:
    value = source.get(key)

    if not isinstance(value, list):
        raise TypeError(f"{key} must be an array: {path}")

    items: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item:
            raise TypeError(f"{key} must contain non-empty strings: {path}")

        items.append(item)

    return tuple(items)


def _required_integer(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer: {path}")

    return value


def _required_positive_integer(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> int:
    value = _required_integer(source, key, path)

    if value <= 0:
        raise ValueError(f"{key} must be positive: {path}")

    return value


def _required_non_negative_integer(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> int:
    value = _required_integer(source, key, path)

    if value < 0:
        raise ValueError(f"{key} must not be negative: {path}")

    return value


def _required_boolean(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> bool:
    value = source.get(key)

    if type(value) is not bool:
        raise TypeError(f"{key} must be a boolean: {path}")

    return value
