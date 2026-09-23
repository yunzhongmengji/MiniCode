"""Summarize recorded Coding Agent evaluation results."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from minicode.context_experiment_protocol import (
    load_budgeted_context_experiment_protocol,
)
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)
from minicode.evaluation_case import EvaluationCaseManifestV3
from minicode.evaluation_formal import validate_budgeted_formal_evidence
from minicode.evaluation_preflight import validate_budgeted_preflight_evidence


@dataclass(frozen=True, slots=True)
class _RecordedContextExperiment:
    protocol_id: str
    arm: str
    max_inline_tool_result_bytes: int | None
    trace_configuration_schema_version: int | None
    strategy: str
    minimum_net_savings_bytes: int | None
    retrieval_tool_loading: str | None
    max_request_bytes: int | None
    budgeted_configuration: BudgetedContextProjectionConfiguration | None
    model_call_count: int
    model_visible_bytes: int
    canonical_bytes: int
    projection_bytes_saved: int
    changed_tool_result_count: int
    successful_readback_count: int
    failed_readback_count: int
    cancelled_readback_count: int


@dataclass(frozen=True, slots=True)
class _RecordedEvaluation:
    case_id: str
    outcome_passed: bool
    operational_passed: bool
    budget_passed: bool | None
    trace_passed: bool | None
    process_coverage_passed: bool | None
    trace_safety_passed: bool | None
    passed: bool
    agent_exit_code: int
    model: str
    minicode_commit: str
    minicode_dirty: bool
    run_outcome: str
    model_call_count: int
    tool_execution_count: int
    input_tokens: int
    output_tokens: int
    workspace_change_count: int
    artifact_names: frozenset[str]
    run_id: str | None
    context_experiment: _RecordedContextExperiment | None


@dataclass(frozen=True, slots=True)
class _ContextPreflightPlan:
    case_id: str
    arm_order: tuple[str, ...]
    maximum_runs: int
    required_safe_successes_per_arm: int
    minimum_changed_tool_result_count: int
    maximum_failed_or_cancelled_readbacks: int
    provider_usage_required: bool
    complete_artifact_set_required: bool
    maximum_input_tokens: int
    maximum_output_tokens: int


@dataclass(frozen=True, slots=True)
class _ContextProtocol:
    protocol_id: str
    model_name: str
    cases: tuple[str, ...]
    baseline_threshold: int | None
    projection_threshold: int | None
    context_projection_configuration_schema_version: int | None
    baseline_strategy: str | None
    projection_strategy: str | None
    baseline_minimum_net_savings_bytes: int | None
    projection_minimum_net_savings_bytes: int | None
    baseline_retrieval_tool_loading: str | None
    projection_retrieval_tool_loading: str | None
    repetitions_per_case_per_arm: int
    required_safe_task_successes_per_arm: int
    minimum_aggregate_input_token_reduction_percent: int
    maximum_per_case_input_token_regression_percent: int
    maximum_failed_or_cancelled_readbacks: int
    preflight_plan: _ContextPreflightPlan | None
    budgeted_projection_configuration: (
        BudgetedContextProjectionConfiguration | None
    ) = None


def summarize_results(results_root: Path) -> str:
    """Render a Markdown summary of every result below one directory."""
    result_paths = tuple(sorted(results_root.rglob("result.json")))

    if not result_paths:
        raise ValueError(f"no result.json files found below {results_root}")

    results = tuple(_load_result(path) for path in result_paths)
    rows = [
        "| Case | Passed | Model calls | Tool executions | Input tokens | Output tokens | Changes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for result in results:
        rows.append(
            "| "
            f"{result.case_id} | "
            f"{'yes' if result.passed else 'no'} | "
            f"{result.model_call_count} | "
            f"{result.tool_execution_count} | "
            f"{result.input_tokens} | "
            f"{result.output_tokens} | "
            f"{result.workspace_change_count} |"
        )

    passed_count = sum(result.passed for result in results)
    outcome_failure_count = sum(not result.outcome_passed for result in results)
    operational_failure_count = sum(not result.operational_passed for result in results)
    budget_failure_count = sum(result.budget_passed is False for result in results)
    unknown_budget_count = sum(result.budget_passed is None for result in results)
    trace_failure_count = sum(result.trace_passed is False for result in results)
    unknown_trace_count = sum(result.trace_passed is None for result in results)
    rate = passed_count / len(results) * 100
    models = ", ".join(sorted({result.model for result in results}))
    commits = ", ".join(sorted({result.minicode_commit[:7] for result in results}))

    rows.extend(
        (
            "",
            f"- Runs: {len(results)}",
            f"- Passed: {passed_count}/{len(results)} ({rate:.1f}%)",
            f"- Outcome failures: {outcome_failure_count}",
            f"- Operational failures: {operational_failure_count}",
            f"- Budget failures: {budget_failure_count}",
            f"- Trace failures: {trace_failure_count}",
            f"- Legacy results without budget verdict: {unknown_budget_count}",
            f"- Legacy results without trace verdict: {unknown_trace_count}",
            f"- Dirty MiniCode runs: {sum(result.minicode_dirty for result in results)}",
            f"- Total model calls: {sum(result.model_call_count for result in results)}",
            f"- Total tool executions: {sum(result.tool_execution_count for result in results)}",
            f"- Total input tokens: {sum(result.input_tokens for result in results)}",
            f"- Total output tokens: {sum(result.output_tokens for result in results)}",
            f"- Models: {models}",
            f"- MiniCode commits: {commits}",
        )
    )
    return "\n".join(rows)


def _validate_context_result_against_protocol(
    result: _RecordedEvaluation,
    protocol: _ContextProtocol,
) -> tuple[_RecordedContextExperiment, str]:
    """Validate facts shared by formal and Preflight context summaries."""
    experiment = result.context_experiment

    if experiment is None:
        raise ValueError("context summary cannot include a non-experiment result")

    if experiment.protocol_id != protocol.protocol_id:
        raise ValueError("result context protocol_id does not match protocol file")

    if result.case_id not in protocol.cases:
        raise ValueError(f"unexpected context experiment case: {result.case_id}")

    budgeted_configuration = protocol.budgeted_projection_configuration

    if budgeted_configuration is not None:
        if experiment.arm == "baseline":
            if (
                experiment.trace_configuration_schema_version != 2
                or experiment.strategy != "identity"
                or experiment.max_inline_tool_result_bytes is not None
                or experiment.budgeted_configuration is not None
                or experiment.changed_tool_result_count != 0
                or experiment.projection_bytes_saved != 0
            ):
                raise ValueError(
                    "baseline result does not match the registered identity arm"
                )
        elif (
            experiment.trace_configuration_schema_version != 3
            or experiment.budgeted_configuration != budgeted_configuration
            or experiment.max_request_bytes
            != budgeted_configuration.max_request_bytes
        ):
            raise ValueError(
                "projection result does not match the registered budgeted arm"
            )
    else:
        expected_threshold = (
            protocol.baseline_threshold
            if experiment.arm == "baseline"
            else protocol.projection_threshold
        )

        if experiment.max_inline_tool_result_bytes != expected_threshold:
            raise ValueError("result context threshold does not match protocol file")

    if (
        budgeted_configuration is None
        and protocol.context_projection_configuration_schema_version is not None
    ):
        expected_strategy = (
            protocol.baseline_strategy
            if experiment.arm == "baseline"
            else protocol.projection_strategy
        )
        expected_minimum_net_savings = (
            protocol.baseline_minimum_net_savings_bytes
            if experiment.arm == "baseline"
            else protocol.projection_minimum_net_savings_bytes
        )
        expected_retrieval_tool_loading = (
            protocol.baseline_retrieval_tool_loading
            if experiment.arm == "baseline"
            else protocol.projection_retrieval_tool_loading
        )

        if (
            experiment.trace_configuration_schema_version
            != protocol.context_projection_configuration_schema_version
            or experiment.strategy != expected_strategy
            or experiment.minimum_net_savings_bytes != expected_minimum_net_savings
            or experiment.retrieval_tool_loading != expected_retrieval_tool_loading
        ):
            raise ValueError(
                "result context configuration does not match protocol file"
            )

    if result.model != protocol.model_name:
        raise ValueError("result model does not match context protocol")

    if result.minicode_dirty:
        raise ValueError("context experiment contains a dirty MiniCode run")

    if result.input_tokens <= 0:
        raise ValueError("context experiment requires positive Provider input tokens")

    if result.output_tokens < 0:
        raise ValueError("context experiment output tokens must not be negative")

    if experiment.model_call_count != result.model_call_count:
        raise ValueError("context and run model-call counts disagree")

    if result.run_id is None:
        raise ValueError("context experiment result must contain a run_id")

    return experiment, result.run_id


def summarize_context_preflight_results(
    results_root: Path,
    protocol_path: Path,
) -> str:
    """Render and gate one two-arm context Preflight batch."""
    protocol = _load_preflight_context_protocol(protocol_path)
    plan = protocol.preflight_plan

    if plan is None:
        raise ValueError("context protocol does not define a Preflight plan")

    orchestration_evidence = (
        validate_budgeted_preflight_evidence(
            results_root=results_root,
            protocol_path=protocol_path,
        )
        if protocol.budgeted_projection_configuration is not None
        else None
    )
    result_paths = tuple(sorted(results_root.rglob("result.json")))

    if not result_paths:
        raise ValueError(f"no result.json files found below {results_root}")

    recorded_results = tuple((path, _load_result(path)) for path in result_paths)
    results = tuple(result for _, result in recorded_results)
    grouped: dict[str, list[tuple[_RecordedEvaluation, _RecordedContextExperiment]]] = {
        "baseline": [],
        "projection": [],
    }
    run_ids: set[str] = set()
    commits: set[str] = set()
    expected_run_by_path = (
        {}
        if orchestration_evidence is None
        else {
            run.result_path.resolve(): run for run in orchestration_evidence.runs
        }
    )
    result_arm_order_gate = True

    for result_path, result in recorded_results:
        experiment, run_id = _validate_context_result_against_protocol(
            result,
            protocol,
        )

        if orchestration_evidence is not None:
            expected_run = expected_run_by_path.get(result_path.resolve())

            if expected_run is None or experiment.arm != expected_run.arm:
                result_arm_order_gate = False

        if result.case_id != plan.case_id:
            raise ValueError("Preflight result uses a case outside the Preflight plan")

        if run_id in run_ids:
            raise ValueError(f"duplicate context experiment run_id: {run_id}")

        run_ids.add(run_id)
        commits.add(result.minicode_commit)
        grouped[experiment.arm].append((result, experiment))

    if len(commits) != 1:
        raise ValueError("context Preflight results must use one MiniCode commit")

    expected_arm_counts = {
        arm: plan.arm_order.count(arm) for arm in ("baseline", "projection")
    }
    run_shape_gate = len(results) == plan.maximum_runs and all(
        len(grouped[arm]) == expected_arm_counts[arm]
        for arm in ("baseline", "projection")
    )
    safe_successes = {
        arm: sum(result.passed for result, _ in grouped[arm])
        for arm in ("baseline", "projection")
    }
    safe_success_gate = all(
        safe_successes[arm] == plan.required_safe_successes_per_arm
        for arm in ("baseline", "projection")
    )
    projection_changes = sum(
        experiment.changed_tool_result_count for _, experiment in grouped["projection"]
    )
    projection_activity_gate = (
        projection_changes >= plan.minimum_changed_tool_result_count
    )
    failed_readbacks = sum(
        experiment.failed_readback_count
        for arm_results in grouped.values()
        for _, experiment in arm_results
    )
    cancelled_readbacks = sum(
        experiment.cancelled_readback_count
        for arm_results in grouped.values()
        for _, experiment in arm_results
    )
    readback_gate = (
        failed_readbacks + cancelled_readbacks
        <= plan.maximum_failed_or_cancelled_readbacks
    )
    input_tokens = sum(result.input_tokens for result in results)
    output_tokens = sum(result.output_tokens for result in results)
    input_budget_gate = input_tokens <= plan.maximum_input_tokens
    output_budget_gate = output_tokens <= plan.maximum_output_tokens
    usage_gate = not plan.provider_usage_required or all(
        result.input_tokens > 0 and result.output_tokens >= 0 for result in results
    )
    required_artifacts = frozenset(("answer", "trace", "workspace_patch"))
    artifact_gate = not plan.complete_artifact_set_required or all(
        required_artifacts <= result.artifact_names for result in results
    )
    protocol_snapshot_path = results_root / "protocol.snapshot.json"
    protocol_snapshot_gate = not plan.complete_artifact_set_required or (
        protocol_snapshot_path.is_file()
        and protocol_snapshot_path.read_bytes() == protocol_path.read_bytes()
    )
    orchestration_gate = orchestration_evidence is None or (
        orchestration_evidence.passed and result_arm_order_gate
    )
    preflight_passed = all(
        (
            run_shape_gate,
            safe_success_gate,
            projection_activity_gate,
            readback_gate,
            input_budget_gate,
            output_budget_gate,
            usage_gate,
            artifact_gate,
            protocol_snapshot_gate,
            orchestration_gate,
        )
    )
    rows = [
        "| Arm | Runs | Safe success | Input tokens | Output tokens | Changed ToolResults | Readbacks failed/cancelled |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for arm in ("baseline", "projection"):
        arm_results = grouped[arm]
        rows.append(
            "| "
            f"{arm} | {len(arm_results)} | "
            f"{safe_successes[arm]}/{plan.required_safe_successes_per_arm} | "
            f"{sum(result.input_tokens for result, _ in arm_results)} | "
            f"{sum(result.output_tokens for result, _ in arm_results)} | "
            f"{sum(experiment.changed_tool_result_count for _, experiment in arm_results)} | "
            f"{sum(experiment.failed_readback_count for _, experiment in arm_results)}/"
            f"{sum(experiment.cancelled_readback_count for _, experiment in arm_results)} |"
        )

    commit = next(iter(commits))
    summary_facts = [
        "",
        f"- Protocol: {protocol.protocol_id}",
        f"- Case: {plan.case_id}",
        f"- Model: {protocol.model_name}",
        f"- MiniCode commit: {commit[:7]}",
        f"- Run shape: {'pass' if run_shape_gate else 'fail'}",
        f"- Safe Task Success: {'pass' if safe_success_gate else 'fail'}",
        (
            "- Projection activity: "
            f"{projection_changes}/{plan.minimum_changed_tool_result_count} "
            f"({'pass' if projection_activity_gate else 'fail'})"
        ),
        (
            "- Failed or cancelled readbacks: "
            f"{failed_readbacks + cancelled_readbacks}/"
            f"{plan.maximum_failed_or_cancelled_readbacks} "
            f"({'pass' if readback_gate else 'fail'})"
        ),
        (
            f"- Provider input Token budget: {input_tokens}/"
            f"{plan.maximum_input_tokens} "
            f"({'pass' if input_budget_gate else 'fail'})"
        ),
        (
            f"- Provider output Token budget: {output_tokens}/"
            f"{plan.maximum_output_tokens} "
            f"({'pass' if output_budget_gate else 'fail'})"
        ),
        f"- Provider Usage present: {'pass' if usage_gate else 'fail'}",
        f"- Per-run Artifact set: {'pass' if artifact_gate else 'fail'}",
        f"- Protocol snapshot: {'pass' if protocol_snapshot_gate else 'fail'}",
    ]

    if orchestration_evidence is not None:
        summary_facts.append(
            f"- Orchestration evidence: {'pass' if orchestration_gate else 'fail'}"
        )

    summary_facts.append(
        f"- Preflight gate: {'PASS' if preflight_passed else 'FAIL'}"
    )
    rows.extend(summary_facts)
    return "\n".join(rows)


def summarize_context_experiment_results(
    results_root: Path,
    protocol_path: Path,
) -> str:
    """Render and gate one formal context-projection A/B result batch."""
    protocol = _load_formal_context_protocol(protocol_path)
    registered_protocol = (
        load_budgeted_context_experiment_protocol(protocol_path)
        if protocol.budgeted_projection_configuration is not None
        else None
    )
    orchestration_evidence = (
        validate_budgeted_formal_evidence(
            results_root=results_root,
            protocol_path=protocol_path,
        )
        if registered_protocol is not None
        else None
    )
    result_paths = tuple(sorted(results_root.rglob("result.json")))

    if not result_paths:
        raise ValueError(f"no result.json files found below {results_root}")

    recorded_results = tuple((path, _load_result(path)) for path in result_paths)
    results = tuple(result for _, result in recorded_results)
    grouped: dict[tuple[str, str], list[_RecordedEvaluation]] = {
        (case_id, arm): []
        for case_id in protocol.cases
        for arm in ("baseline", "projection")
    }
    run_ids: set[str] = set()
    commits: set[str] = set()
    expected_run_by_path = (
        {}
        if orchestration_evidence is None
        else {
            run.result_path.resolve(): run for run in orchestration_evidence.runs
        }
    )
    result_order_gate = True

    for result_path, result in recorded_results:
        experiment, run_id = _validate_context_result_against_protocol(
            result,
            protocol,
        )

        if orchestration_evidence is not None:
            expected_run = expected_run_by_path.get(result_path.resolve())

            if (
                expected_run is None
                or result.case_id != expected_run.case_id
                or experiment.arm != expected_run.arm
            ):
                result_order_gate = False

        if run_id in run_ids:
            raise ValueError(f"duplicate context experiment run_id: {run_id}")

        run_ids.add(run_id)
        commits.add(result.minicode_commit)
        grouped[(result.case_id, experiment.arm)].append(result)

    if len(commits) != 1:
        raise ValueError("context experiment results must use one MiniCode commit")

    rows = [
        "| Case | Arm | Runs | Safe success | Input tokens | Output tokens | Readbacks ok/failed/cancelled |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    repetition_complete = True
    safe_successes = {"baseline": 0, "projection": 0}
    task_outcomes = {"baseline": 0, "projection": 0}
    operational_budget_successes = {"baseline": 0, "projection": 0}
    trace_compliances = {"baseline": 0, "projection": 0}
    process_coverages = {"baseline": 0, "projection": 0}
    trace_safety_successes = {"baseline": 0, "projection": 0}
    candidate_v5_safe_successes = {"baseline": 0, "projection": 0}
    input_tokens = {"baseline": 0, "projection": 0}
    output_tokens = {"baseline": 0, "projection": 0}
    failed_or_cancelled_readbacks = 0
    case_token_rows: list[str] = []
    per_case_token_gate = True

    for case_id in protocol.cases:
        for arm in ("baseline", "projection"):
            arm_results = grouped[(case_id, arm)]
            experiment_records = tuple(
                result.context_experiment
                for result in arm_results
                if result.context_experiment is not None
            )
            run_count = len(arm_results)
            passed_count = sum(result.passed for result in arm_results)
            task_outcome_count = sum(result.outcome_passed for result in arm_results)
            operational_budget_count = sum(
                result.operational_passed and result.budget_passed is True
                for result in arm_results
            )
            trace_compliance_count = sum(
                result.trace_passed is True for result in arm_results
            )
            process_coverage_count = sum(
                result.process_coverage_passed is True for result in arm_results
            )
            trace_safety_count = sum(
                result.trace_safety_passed is True for result in arm_results
            )
            candidate_v5_safe_count = sum(
                result.outcome_passed
                and result.operational_passed
                and result.budget_passed is True
                and result.trace_safety_passed is True
                for result in arm_results
            )
            arm_input_tokens = sum(result.input_tokens for result in arm_results)
            arm_output_tokens = sum(result.output_tokens for result in arm_results)
            successful_readbacks = sum(
                record.successful_readback_count for record in experiment_records
            )
            failed_readbacks = sum(
                record.failed_readback_count for record in experiment_records
            )
            cancelled_readbacks = sum(
                record.cancelled_readback_count for record in experiment_records
            )
            repetition_complete = repetition_complete and (
                run_count == protocol.repetitions_per_case_per_arm
            )
            safe_successes[arm] += passed_count
            task_outcomes[arm] += task_outcome_count
            operational_budget_successes[arm] += operational_budget_count
            trace_compliances[arm] += trace_compliance_count
            process_coverages[arm] += process_coverage_count
            trace_safety_successes[arm] += trace_safety_count
            candidate_v5_safe_successes[arm] += candidate_v5_safe_count
            input_tokens[arm] += arm_input_tokens
            output_tokens[arm] += arm_output_tokens
            failed_or_cancelled_readbacks += failed_readbacks + cancelled_readbacks
            rows.append(
                "| "
                f"{case_id} | {arm} | {run_count} | {passed_count}/{run_count} | "
                f"{arm_input_tokens} | {arm_output_tokens} | "
                f"{successful_readbacks}/{failed_readbacks}/{cancelled_readbacks} |"
            )

        baseline_tokens = sum(
            result.input_tokens for result in grouped[(case_id, "baseline")]
        )
        projection_tokens = sum(
            result.input_tokens for result in grouped[(case_id, "projection")]
        )

        if baseline_tokens <= 0:
            case_change = None
            case_gate = False
        else:
            case_change = (projection_tokens - baseline_tokens) / baseline_tokens * 100
            case_gate = (
                case_change <= protocol.maximum_per_case_input_token_regression_percent
            )

        per_case_token_gate = per_case_token_gate and case_gate
        rendered_change = "n/a" if case_change is None else f"{case_change:+.1f}%"
        case_token_rows.append(
            "| "
            f"{case_id} | {baseline_tokens} | {projection_tokens} | "
            f"{rendered_change} | {'pass' if case_gate else 'fail'} |"
        )

    baseline_total = input_tokens["baseline"]
    projection_total = input_tokens["projection"]
    aggregate_reduction = (
        (baseline_total - projection_total) / baseline_total * 100
        if baseline_total > 0
        else None
    )
    aggregate_token_gate = (
        aggregate_reduction is not None
        and aggregate_reduction
        >= protocol.minimum_aggregate_input_token_reduction_percent
    )
    safe_success_gate = all(
        safe_successes[arm] == protocol.required_safe_task_successes_per_arm
        for arm in ("baseline", "projection")
    )
    readback_gate = (
        failed_or_cancelled_readbacks <= protocol.maximum_failed_or_cancelled_readbacks
    )
    total_input_tokens = sum(input_tokens.values())
    total_output_tokens = sum(output_tokens.values())
    formal_input_budget_gate = (
        registered_protocol is None
        or total_input_tokens
        <= registered_protocol.formal_budget.maximum_input_tokens
    )
    formal_output_budget_gate = (
        registered_protocol is None
        or total_output_tokens
        <= registered_protocol.formal_budget.maximum_output_tokens
    )
    orchestration_gate = orchestration_evidence is None or (
        orchestration_evidence.passed and result_order_gate
    )
    advancement_passed = all(
        (
            repetition_complete,
            safe_success_gate,
            aggregate_token_gate,
            per_case_token_gate,
            readback_gate,
            formal_input_budget_gate,
            formal_output_budget_gate,
            orchestration_gate,
        )
    )
    rendered_reduction = (
        "n/a" if aggregate_reduction is None else f"{aggregate_reduction:.1f}%"
    )
    commit = next(iter(commits))
    rows.extend(
        (
            "",
            "| Case | Baseline input | Projection input | Projection change | Per-case gate |",
            "|---|---:|---:|---:|---:|",
            *case_token_rows,
            "",
            f"- Protocol: {protocol.protocol_id}",
            f"- Model: {protocol.model_name}",
            f"- MiniCode commit: {commit[:7]}",
            f"- Formal runs: {len(results)}",
            f"- Repetitions complete: {'yes' if repetition_complete else 'no'}",
            (
                "- Task Outcome: "
                f"baseline {task_outcomes['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {task_outcomes['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Operational/Budget: "
                f"baseline {operational_budget_successes['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {operational_budget_successes['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Trace Compliance: "
                f"baseline {trace_compliances['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {trace_compliances['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Process Coverage (diagnostic): "
                f"baseline {process_coverages['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {process_coverages['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Trace Safety (forbidden requests + post-change test): "
                f"baseline {trace_safety_successes['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {trace_safety_successes['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Candidate v5 Safe Task Success (not a gate): "
                f"baseline {candidate_v5_safe_successes['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {candidate_v5_safe_successes['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm}"
            ),
            (
                "- Safe Task Success (frozen composite): "
                f"baseline {safe_successes['baseline']}/"
                f"{protocol.required_safe_task_successes_per_arm}, "
                f"projection {safe_successes['projection']}/"
                f"{protocol.required_safe_task_successes_per_arm} "
                f"({'pass' if safe_success_gate else 'fail'})"
            ),
            (
                "- Aggregate input Token reduction: "
                f"{rendered_reduction} "
                f"({'pass' if aggregate_token_gate else 'fail'})"
            ),
            (
                "- Per-case input Token guardrail: "
                f"{'pass' if per_case_token_gate else 'fail'}"
            ),
            (
                "- Failed or cancelled readbacks: "
                f"{failed_or_cancelled_readbacks} "
                f"({'pass' if readback_gate else 'fail'})"
            ),
        )
    )

    if registered_protocol is not None:
        rows.extend(
            (
                (
                    "- Provider input Token budget: "
                    f"{total_input_tokens}/"
                    f"{registered_protocol.formal_budget.maximum_input_tokens} "
                    f"({'pass' if formal_input_budget_gate else 'fail'})"
                ),
                (
                    "- Provider output Token budget: "
                    f"{total_output_tokens}/"
                    f"{registered_protocol.formal_budget.maximum_output_tokens} "
                    f"({'pass' if formal_output_budget_gate else 'fail'})"
                ),
                (
                    "- Orchestration evidence: "
                    f"{'pass' if orchestration_gate else 'fail'}"
                ),
            )
        )

    rows.append(
        f"- Advancement gate: {'PASS' if advancement_passed else 'FAIL'}"
    )
    return "\n".join(rows)


def _load_result(path: Path) -> _RecordedEvaluation:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"evaluation result must be an object: {path}")

    result = cast(Mapping[str, object], decoded)
    schema_version = _required_integer(result, "schema_version", path)

    if schema_version not in (1, 2):
        raise ValueError(
            f"unsupported evaluation result schema {schema_version}: {path}"
        )

    run = _required_mapping(result, "run", path)
    artifact_names = _verify_artifacts(result, path)
    accepted = _required_boolean(result, "accepted", path)
    agent_exit_code = _required_integer(result, "agent_exit_code", path)
    run_outcome = _required_string(run, "outcome", path)
    verdict = result.get("verdict")

    if verdict is None:
        if schema_version == 2:
            raise ValueError(f"schema 2 result must contain a verdict: {path}")

        outcome_passed = accepted
        operational_passed = agent_exit_code == 0 and run_outcome == "succeeded"
        budget_passed = None
        trace_passed = None
        passed = accepted
    else:
        if not isinstance(verdict, Mapping):
            raise TypeError(f"verdict must be an object: {path}")

        typed_verdict = cast(Mapping[str, object], verdict)
        outcome_passed = _required_boolean(
            typed_verdict,
            "outcome_passed",
            path,
        )
        operational_passed = _required_boolean(
            typed_verdict,
            "operational_passed",
            path,
        )
        budget_passed = _required_boolean(
            typed_verdict,
            "budget_passed",
            path,
        )
        trace_passed = (
            _required_boolean(
                typed_verdict,
                "trace_passed",
                path,
            )
            if schema_version == 2
            else None
        )
        passed = _required_boolean(
            typed_verdict,
            "passed",
            path,
        )

        if outcome_passed != accepted:
            raise ValueError(f"verdict outcome disagrees with accepted: {path}")

        expected_passed = outcome_passed and operational_passed and budget_passed

        if trace_passed is not None:
            expected_passed = expected_passed and trace_passed

        if passed != expected_passed:
            raise ValueError(f"verdict passed is inconsistent: {path}")

    workspace_status = result.get("workspace_status")

    if not isinstance(workspace_status, list):
        raise TypeError(f"workspace_status must be a list: {path}")

    context_experiment = _load_recorded_context_experiment(
        result.get("context_experiment"),
        path,
    )
    case_id = _required_string(result, "case_id", path)
    process_coverage_passed, trace_safety_passed = _load_trace_dimensions(
        result,
        case_id=case_id,
        schema_version=schema_version,
        trace_passed=trace_passed,
        path=path,
    )

    return _RecordedEvaluation(
        case_id=case_id,
        outcome_passed=outcome_passed,
        operational_passed=operational_passed,
        budget_passed=budget_passed,
        trace_passed=trace_passed,
        process_coverage_passed=process_coverage_passed,
        trace_safety_passed=trace_safety_passed,
        passed=passed,
        agent_exit_code=agent_exit_code,
        model=_required_string(result, "model", path),
        minicode_commit=_required_string(result, "minicode_commit", path),
        minicode_dirty=_required_boolean(result, "minicode_dirty", path),
        run_outcome=run_outcome,
        model_call_count=_required_integer(run, "model_call_count", path),
        tool_execution_count=_required_integer(
            run,
            "tool_execution_count",
            path,
        ),
        input_tokens=_required_integer(run, "input_tokens", path),
        output_tokens=_required_integer(run, "output_tokens", path),
        workspace_change_count=len(workspace_status),
        artifact_names=artifact_names,
        run_id=_optional_string(run, "run_id", path),
        context_experiment=context_experiment,
    )


def _load_trace_dimensions(
    result: Mapping[str, object],
    *,
    case_id: str,
    schema_version: int,
    trace_passed: bool | None,
    path: Path,
) -> tuple[bool | None, bool | None]:
    """Split recorded trace facts into process coverage and safety dimensions."""
    trace_evaluation = result.get("trace_evaluation")

    if trace_evaluation is None:
        if schema_version == 2:
            raise ValueError(f"schema 2 result must contain trace_evaluation: {path}")

        return None, None

    if not isinstance(trace_evaluation, Mapping):
        raise TypeError(f"trace_evaluation must be an object: {path}")

    details = cast(Mapping[str, object], trace_evaluation)
    # The persisted schema-2 field name is retained for compatibility.  Once
    # loaded, the value represents process coverage for both case schemas.
    missing_process_tools = _required_string_sequence(
        details,
        "missing_required_tools",
        path,
    )
    requested_forbidden_tools = _required_string_sequence(
        details,
        "requested_forbidden_tools",
        path,
    )
    successful_test_after_last_change = details.get("successful_test_after_last_change")

    if (
        successful_test_after_last_change is not None
        and type(successful_test_after_last_change) is not bool
    ):
        raise TypeError(
            f"successful_test_after_last_change must be a boolean or null: {path}"
        )

    _validate_schema_3_trace_dimensions(
        result,
        case_id=case_id,
        missing_process_tools=missing_process_tools,
        requested_forbidden_tools=requested_forbidden_tools,
        successful_test_after_last_change=successful_test_after_last_change,
        path=path,
    )

    process_coverage_passed = not missing_process_tools
    trace_safety_passed = (
        not requested_forbidden_tools and successful_test_after_last_change is not False
    )
    detailed_trace_passed = process_coverage_passed and trace_safety_passed

    if trace_passed is not None and detailed_trace_passed != trace_passed:
        raise ValueError(f"trace details disagree with verdict: {path}")

    return process_coverage_passed, trace_safety_passed


def _validate_schema_3_trace_dimensions(
    result: Mapping[str, object],
    *,
    case_id: str,
    missing_process_tools: tuple[str, ...],
    requested_forbidden_tools: tuple[str, ...],
    successful_test_after_last_change: object,
    path: Path,
) -> None:
    """Cross-check classified trace facts against the recorded case contract."""
    case_manifest = result.get("case_manifest")

    if case_manifest is None:
        return

    if not isinstance(case_manifest, Mapping):
        raise TypeError(f"case_manifest must be an object: {path}")

    untyped_manifest = cast(Mapping[str, object], case_manifest)

    if untyped_manifest.get("schema_version") != 3:
        return

    manifest = EvaluationCaseManifestV3.model_validate_json(
        json.dumps(untyped_manifest)
    )

    if manifest.case_id != case_id:
        raise ValueError(f"case manifest id disagrees with result: {path}")

    expectations = manifest.trace_expectations
    unexpected_missing = tuple(
        tool
        for tool in missing_process_tools
        if tool not in expectations.process_coverage_tools
    )

    if unexpected_missing:
        raise ValueError(
            "missing process tools are not declared by the case manifest: "
            f"{unexpected_missing}: {path}"
        )

    unexpected_forbidden = tuple(
        tool
        for tool in requested_forbidden_tools
        if tool not in expectations.forbidden_tool_requests
    )

    if unexpected_forbidden:
        raise ValueError(
            "requested forbidden tools are not declared by the case manifest: "
            f"{unexpected_forbidden}: {path}"
        )

    if (
        not expectations.require_successful_test_after_change
        and successful_test_after_last_change is not None
    ):
        raise ValueError(
            "post-change test result exists when the case does not require it: "
            f"{path}"
        )


def _load_recorded_context_experiment(
    value: object,
    path: Path,
) -> _RecordedContextExperiment | None:
    if value is None:
        return None

    if not isinstance(value, Mapping):
        raise TypeError(f"context_experiment must be an object: {path}")

    experiment = cast(Mapping[str, object], value)
    arm = _required_string(experiment, "arm", path)

    if arm not in ("baseline", "projection"):
        raise ValueError(f"unknown context experiment arm {arm}: {path}")

    threshold = experiment.get("max_inline_tool_result_bytes")

    if threshold is not None and type(threshold) is not int:
        raise TypeError(
            f"max_inline_tool_result_bytes must be an integer or null: {path}"
        )

    trace_configuration = _required_mapping(
        experiment,
        "trace_configuration",
        path,
    )
    configuration_schema_version = trace_configuration.get(
        "configuration_schema_version"
    )
    recorded_configuration_schema_version: int | None = None
    recorded_minimum_net_savings: int | None = None
    recorded_retrieval_tool_loading: str | None = None
    recorded_max_request_bytes: int | None = None
    budgeted_configuration: BudgetedContextProjectionConfiguration | None = None

    if configuration_schema_version == 3:
        if arm != "projection":
            raise ValueError(
                f"schema-3 context trace must use the projection arm: {path}"
            )

        if "max_inline_tool_result_bytes" in experiment:
            raise ValueError(
                f"schema-3 context result must not contain a threshold: {path}"
            )

        budgeted_configuration = (
            BudgetedContextProjectionConfiguration.from_payload(
                trace_configuration
            )
        )
        recorded_max_request_bytes = _required_positive_integer(
            experiment,
            "max_request_bytes",
            path,
        )

        if (
            recorded_max_request_bytes
            != budgeted_configuration.max_request_bytes
        ):
            raise ValueError(
                f"context trace request budget disagrees with result: {path}"
            )

        expected_strategy = "budgeted_tool_result_reference"
        recorded_configuration_schema_version = 3
        recorded_minimum_net_savings = (
            budgeted_configuration.minimum_net_savings_bytes
        )
        recorded_retrieval_tool_loading = (
            budgeted_configuration.retrieval_tool_loading
        )
    else:
        expected_strategy = (
            "identity" if arm == "baseline" else "tool_result_reference"
        )

        if trace_configuration.get("max_inline_tool_result_bytes") != threshold:
            raise ValueError(f"context trace threshold disagrees with result: {path}")

        if configuration_schema_version is not None and configuration_schema_version != 2:
            raise ValueError(f"unknown context trace configuration schema: {path}")

    if _required_string(trace_configuration, "strategy", path) != expected_strategy:
        raise ValueError(f"context trace strategy disagrees with arm: {path}")

    if configuration_schema_version == 2:

        expected_minimum_net_savings = None if arm == "baseline" else 1
        expected_retrieval_tool_loading = None if arm == "baseline" else "on_reference"

        for field in ("minimum_net_savings_bytes", "retrieval_tool_loading"):
            if field not in trace_configuration:
                raise ValueError(
                    f"context trace configuration is missing {field}: {path}"
                )

        if (
            trace_configuration.get("minimum_net_savings_bytes")
            != expected_minimum_net_savings
        ):
            raise ValueError(f"context trace net-savings gate disagrees: {path}")

        if (
            trace_configuration.get("retrieval_tool_loading")
            != expected_retrieval_tool_loading
        ):
            raise ValueError(f"context trace retrieval-tool loading disagrees: {path}")

        recorded_configuration_schema_version = 2
        recorded_minimum_net_savings = expected_minimum_net_savings
        recorded_retrieval_tool_loading = expected_retrieval_tool_loading

    metrics = _required_mapping(experiment, "metrics", path)
    record = _RecordedContextExperiment(
        protocol_id=_required_string(experiment, "protocol_id", path),
        arm=arm,
        max_inline_tool_result_bytes=threshold,
        trace_configuration_schema_version=recorded_configuration_schema_version,
        strategy=expected_strategy,
        minimum_net_savings_bytes=recorded_minimum_net_savings,
        retrieval_tool_loading=recorded_retrieval_tool_loading,
        max_request_bytes=recorded_max_request_bytes,
        budgeted_configuration=budgeted_configuration,
        model_call_count=_required_positive_integer(metrics, "model_call_count", path),
        model_visible_bytes=_required_non_negative_integer(
            metrics, "model_visible_bytes", path
        ),
        canonical_bytes=_required_non_negative_integer(
            metrics, "canonical_bytes", path
        ),
        projection_bytes_saved=_required_non_negative_integer(
            metrics,
            "projection_bytes_saved",
            path,
        ),
        changed_tool_result_count=_required_non_negative_integer(
            metrics,
            "changed_tool_result_count",
            path,
        ),
        successful_readback_count=_required_non_negative_integer(
            metrics,
            "successful_readback_count",
            path,
        ),
        failed_readback_count=_required_non_negative_integer(
            metrics,
            "failed_readback_count",
            path,
        ),
        cancelled_readback_count=_required_non_negative_integer(
            metrics,
            "cancelled_readback_count",
            path,
        ),
    )

    if record.canonical_bytes - record.model_visible_bytes != (
        record.projection_bytes_saved
    ):
        raise ValueError(f"context byte metrics are inconsistent: {path}")

    return record


def _load_preflight_context_protocol(path: Path) -> _ContextProtocol:
    """Load either a historical schema-2 or budgeted schema-3 Preflight."""
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"context protocol must be an object: {path}")

    protocol_payload = cast(Mapping[str, object], decoded)

    if _required_integer(protocol_payload, "schema_version", path) != 3:
        return _load_context_protocol(path)

    protocol = load_budgeted_context_experiment_protocol(path)
    registered_plan = protocol.preflight_plan
    plan = _ContextPreflightPlan(
        case_id=registered_plan.case_id,
        arm_order=registered_plan.arm_order,
        maximum_runs=registered_plan.budget.maximum_runs,
        required_safe_successes_per_arm=(
            registered_plan.required_safe_successes_per_arm
        ),
        minimum_changed_tool_result_count=(
            registered_plan.minimum_changed_tool_result_count
        ),
        maximum_failed_or_cancelled_readbacks=(
            registered_plan.maximum_failed_or_cancelled_readbacks
        ),
        provider_usage_required=registered_plan.provider_usage_required,
        complete_artifact_set_required=(
            registered_plan.complete_artifact_set_required
        ),
        maximum_input_tokens=registered_plan.budget.maximum_input_tokens,
        maximum_output_tokens=registered_plan.budget.maximum_output_tokens,
    )
    gates = protocol.advancement_gates
    return _ContextProtocol(
        protocol_id=protocol.protocol_id,
        model_name=protocol.model.name,
        cases=protocol.cases,
        baseline_threshold=None,
        projection_threshold=None,
        context_projection_configuration_schema_version=None,
        baseline_strategy="identity",
        projection_strategy="budgeted_tool_result_reference",
        baseline_minimum_net_savings_bytes=None,
        projection_minimum_net_savings_bytes=(
            protocol.projection_configuration.minimum_net_savings_bytes
        ),
        baseline_retrieval_tool_loading=None,
        projection_retrieval_tool_loading=(
            protocol.projection_configuration.retrieval_tool_loading
        ),
        repetitions_per_case_per_arm=protocol.repetitions_per_case_per_arm,
        required_safe_task_successes_per_arm=(
            gates.required_safe_task_successes_per_arm
        ),
        minimum_aggregate_input_token_reduction_percent=(
            gates.minimum_aggregate_input_token_reduction_percent
        ),
        maximum_per_case_input_token_regression_percent=(
            gates.maximum_per_case_input_token_regression_percent
        ),
        maximum_failed_or_cancelled_readbacks=(
            gates.maximum_failed_or_cancelled_readbacks
        ),
        preflight_plan=plan,
        budgeted_projection_configuration=protocol.projection_configuration,
    )


def _load_formal_context_protocol(path: Path) -> _ContextProtocol:
    """Load historical formal protocols or the registered budgeted schema."""
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"context protocol must be an object: {path}")

    protocol_payload = cast(Mapping[str, object], decoded)

    if _required_integer(protocol_payload, "schema_version", path) == 3:
        return _load_preflight_context_protocol(path)

    return _load_context_protocol(path)


def _load_context_protocol(path: Path) -> _ContextProtocol:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"context protocol must be an object: {path}")

    protocol = cast(Mapping[str, object], decoded)
    schema_version = _required_integer(protocol, "schema_version", path)

    if schema_version not in (1, 2):
        raise ValueError(f"unsupported context protocol schema: {path}")

    model = _required_mapping(protocol, "model", path)
    arms = _required_mapping(protocol, "arms", path)
    baseline = _required_mapping(arms, "baseline", path)
    projection = _required_mapping(arms, "projection", path)
    advancement_gates = _required_mapping(protocol, "advancement_gates", path)
    cases_value = protocol.get("cases")

    if not isinstance(cases_value, list) or not cases_value:
        raise TypeError(f"context protocol cases must be a non-empty list: {path}")

    cases: list[str] = []

    for case_id in cases_value:
        if not isinstance(case_id, str) or not case_id:
            raise TypeError(f"context protocol case IDs must be strings: {path}")

        cases.append(case_id)

    if len(set(cases)) != len(cases):
        raise ValueError(f"context protocol case IDs must be unique: {path}")

    baseline_threshold = baseline.get("max_inline_tool_result_bytes")
    projection_threshold = projection.get("max_inline_tool_result_bytes")

    if baseline_threshold is not None:
        raise ValueError(f"baseline context threshold must be null: {path}")

    if type(projection_threshold) is not int:
        raise TypeError(f"projection context threshold must be an integer: {path}")

    if projection_threshold < 0:
        raise ValueError(f"projection context threshold cannot be negative: {path}")

    configuration_schema_version: int | None = None
    baseline_strategy: str | None = None
    projection_strategy: str | None = None
    baseline_minimum_net_savings: int | None = None
    projection_minimum_net_savings: int | None = None
    baseline_retrieval_tool_loading: str | None = None
    projection_retrieval_tool_loading: str | None = None
    preflight_plan: _ContextPreflightPlan | None = None

    if schema_version == 2:
        configuration_schema_version = _required_integer(
            protocol,
            "context_projection_configuration_schema_version",
            path,
        )

        if configuration_schema_version != 2:
            raise ValueError(
                f"unsupported context projection configuration schema: {path}"
            )

        baseline_strategy = _required_string(baseline, "strategy", path)
        projection_strategy = _required_string(projection, "strategy", path)

        if baseline_strategy != "identity":
            raise ValueError(f"baseline context strategy must be identity: {path}")

        if projection_strategy != "tool_result_reference":
            raise ValueError(
                f"projection context strategy must use tool-result references: {path}"
            )

        for arm in (baseline, projection):
            for field in (
                "minimum_net_savings_bytes",
                "retrieval_tool_loading",
            ):
                if field not in arm:
                    raise ValueError(
                        f"context protocol arm configuration is missing {field}: {path}"
                    )

        baseline_minimum_value = baseline.get("minimum_net_savings_bytes")
        projection_minimum_value = projection.get("minimum_net_savings_bytes")
        baseline_loading_value = baseline.get("retrieval_tool_loading")
        projection_loading_value = projection.get("retrieval_tool_loading")

        if baseline_minimum_value is not None:
            raise ValueError(f"baseline net-savings gate must be null: {path}")

        if projection_minimum_value != 1:
            raise ValueError(f"projection net-savings gate must be 1: {path}")

        if baseline_loading_value is not None:
            raise ValueError(f"baseline retrieval-tool loading must be null: {path}")

        if projection_loading_value != "on_reference":
            raise ValueError(
                f"projection retrieval tool must load on reference: {path}"
            )

        projection_minimum_net_savings = 1
        projection_retrieval_tool_loading = "on_reference"

        preflight = _required_mapping(protocol, "preflight_plan", path)
        preflight_budget = _required_mapping(protocol, "preflight_budget", path)
        success_requirements = _required_mapping(
            preflight,
            "success_requirements",
            path,
        )
        preflight_case = _required_string(preflight, "case", path)

        if preflight_case not in cases:
            raise ValueError(f"preflight case must be a protocol case: {path}")

        arm_order_value = preflight.get("arm_order")

        if not isinstance(arm_order_value, list) or not arm_order_value:
            raise TypeError(f"preflight arm_order must be a non-empty list: {path}")

        arm_order: list[str] = []

        for arm in arm_order_value:
            if arm not in ("baseline", "projection"):
                raise ValueError(f"preflight arm_order contains unknown arm: {path}")

            arm_order.append(arm)

        preflight_runs = _required_positive_integer(preflight, "runs", path)
        maximum_runs = _required_positive_integer(
            preflight_budget,
            "maximum_runs",
            path,
        )

        if preflight_runs != len(arm_order) or maximum_runs != preflight_runs:
            raise ValueError(
                f"preflight run count must match arm order and budget: {path}"
            )

        required_preflight_successes = _required_positive_integer(
            success_requirements,
            "safe_task_successes_per_arm",
            path,
        )
        arm_counts = {arm: arm_order.count(arm) for arm in ("baseline", "projection")}

        if any(count != required_preflight_successes for count in arm_counts.values()):
            raise ValueError(
                f"preflight safe successes must match each arm count: {path}"
            )

        preflight_plan = _ContextPreflightPlan(
            case_id=preflight_case,
            arm_order=tuple(arm_order),
            maximum_runs=maximum_runs,
            required_safe_successes_per_arm=required_preflight_successes,
            minimum_changed_tool_result_count=_required_positive_integer(
                success_requirements,
                "minimum_changed_tool_result_count",
                path,
            ),
            maximum_failed_or_cancelled_readbacks=(
                _required_non_negative_integer(
                    success_requirements,
                    "maximum_failed_or_cancelled_readbacks",
                    path,
                )
            ),
            provider_usage_required=_required_boolean(
                success_requirements,
                "provider_usage_required",
                path,
            ),
            complete_artifact_set_required=_required_boolean(
                success_requirements,
                "complete_artifact_set_required",
                path,
            ),
            maximum_input_tokens=_required_positive_integer(
                preflight_budget,
                "maximum_input_tokens",
                path,
            ),
            maximum_output_tokens=_required_positive_integer(
                preflight_budget,
                "maximum_output_tokens",
                path,
            ),
        )

    repetitions = _required_positive_integer(
        protocol,
        "repetitions_per_case_per_arm",
        path,
    )
    required_safe_successes = _required_non_negative_integer(
        advancement_gates,
        "required_safe_task_successes_per_arm",
        path,
    )
    expected_safe_successes = len(cases) * repetitions

    if required_safe_successes != expected_safe_successes:
        raise ValueError(
            f"required safe successes must equal cases times repetitions: {path}"
        )

    return _ContextProtocol(
        protocol_id=_required_string(protocol, "protocol_id", path),
        model_name=_required_string(model, "name", path),
        cases=tuple(cases),
        baseline_threshold=None,
        projection_threshold=projection_threshold,
        context_projection_configuration_schema_version=(configuration_schema_version),
        baseline_strategy=baseline_strategy,
        projection_strategy=projection_strategy,
        baseline_minimum_net_savings_bytes=baseline_minimum_net_savings,
        projection_minimum_net_savings_bytes=projection_minimum_net_savings,
        baseline_retrieval_tool_loading=baseline_retrieval_tool_loading,
        projection_retrieval_tool_loading=projection_retrieval_tool_loading,
        repetitions_per_case_per_arm=repetitions,
        required_safe_task_successes_per_arm=required_safe_successes,
        minimum_aggregate_input_token_reduction_percent=(
            _required_non_negative_integer(
                advancement_gates,
                "minimum_aggregate_input_token_reduction_percent",
                path,
            )
        ),
        maximum_per_case_input_token_regression_percent=(
            _required_non_negative_integer(
                advancement_gates,
                "maximum_per_case_input_token_regression_percent",
                path,
            )
        ),
        maximum_failed_or_cancelled_readbacks=_required_non_negative_integer(
            advancement_gates,
            "maximum_failed_or_cancelled_readbacks",
            path,
        ),
        preflight_plan=preflight_plan,
    )


def _verify_artifacts(
    result: Mapping[str, object],
    result_path: Path,
) -> frozenset[str]:
    artifacts = _required_mapping(result, "artifacts", result_path)

    for required_name in ("answer", "trace"):
        if required_name not in artifacts:
            raise ValueError(f"artifacts must contain {required_name}: {result_path}")

    for artifact_name, untyped_metadata in artifacts.items():
        if not isinstance(untyped_metadata, Mapping):
            raise TypeError(
                f"artifact {artifact_name} must be an object: {result_path}"
            )

        metadata = cast(Mapping[str, object], untyped_metadata)
        file_name = _required_string(metadata, "file", result_path)
        expected_sha256 = _required_string(metadata, "sha256", result_path)

        if Path(file_name).name != file_name:
            raise ValueError(
                f"artifact file must be a sibling file name: {result_path}"
            )

        artifact_path = result_path.parent / file_name

        if not artifact_path.is_file():
            raise ValueError(f"artifact file is missing: {artifact_path}")

        actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        if actual_sha256 != expected_sha256:
            raise ValueError(f"artifact SHA-256 mismatch: {artifact_path}")

    return frozenset(artifacts)


def _required_mapping(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> Mapping[str, object]:
    value = source.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object: {path}")

    return cast(Mapping[str, object], value)


def _required_string(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> str:
    value = source.get(key)

    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string: {path}")

    return value


def _required_string_sequence(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> tuple[str, ...]:
    value = source.get(key)

    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be an array of strings: {path}")

    return tuple(value)


def _required_integer(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer: {path}")

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


def _required_positive_integer(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> int:
    value = _required_integer(source, key, path)

    if value <= 0:
        raise ValueError(f"{key} must be positive: {path}")

    return value


def _optional_string(
    source: Mapping[str, object],
    key: str,
    path: Path,
) -> str | None:
    value = source.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string when present: {path}")

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


def build_parser() -> argparse.ArgumentParser:
    """Build the summary command argument parser."""
    parser = argparse.ArgumentParser(
        description="Summarize recorded MiniCode evaluations.",
    )
    parser.add_argument(
        "results_root",
        type=Path,
        help="Directory containing one or more result.json files.",
    )
    context_mode = parser.add_mutually_exclusive_group()
    context_mode.add_argument(
        "--context-protocol",
        type=Path,
        help="Pre-registered context protocol for A/B gate reporting.",
    )
    context_mode.add_argument(
        "--context-preflight-protocol",
        type=Path,
        help="Pre-registered context protocol for two-arm Preflight reporting.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print one summary for a recorded evaluation batch."""
    args = build_parser().parse_args(argv)
    exit_code = 0

    if args.context_preflight_protocol is not None:
        summary = summarize_context_preflight_results(
            args.results_root,
            args.context_preflight_protocol,
        )
        if summary.endswith("- Preflight gate: FAIL"):
            exit_code = 1
    elif args.context_protocol is not None:
        summary = summarize_context_experiment_results(
            args.results_root,
            args.context_protocol,
        )
    else:
        summary = summarize_results(args.results_root)

    print(summary)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
