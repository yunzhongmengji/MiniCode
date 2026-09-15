"""Summarize recorded Coding Agent evaluation results."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True, slots=True)
class _RecordedContextExperiment:
    protocol_id: str
    arm: str
    max_inline_tool_result_bytes: int | None
    trace_configuration_schema_version: int | None
    strategy: str
    minimum_net_savings_bytes: int | None
    retrieval_tool_loading: str | None
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
    run_id: str | None
    context_experiment: _RecordedContextExperiment | None


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


def summarize_context_experiment_results(
    results_root: Path,
    protocol_path: Path,
) -> str:
    """Render and gate one formal context-projection A/B result batch."""
    protocol = _load_context_protocol(protocol_path)
    result_paths = tuple(sorted(results_root.rglob("result.json")))

    if not result_paths:
        raise ValueError(f"no result.json files found below {results_root}")

    results = tuple(_load_result(path) for path in result_paths)
    grouped: dict[tuple[str, str], list[_RecordedEvaluation]] = {
        (case_id, arm): []
        for case_id in protocol.cases
        for arm in ("baseline", "projection")
    }
    run_ids: set[str] = set()
    commits: set[str] = set()

    for result in results:
        experiment = result.context_experiment

        if experiment is None:
            raise ValueError("context summary cannot include a non-experiment result")

        if experiment.protocol_id != protocol.protocol_id:
            raise ValueError("result context protocol_id does not match protocol file")

        if result.case_id not in protocol.cases:
            raise ValueError(f"unexpected context experiment case: {result.case_id}")

        expected_threshold = (
            protocol.baseline_threshold
            if experiment.arm == "baseline"
            else protocol.projection_threshold
        )

        if experiment.max_inline_tool_result_bytes != expected_threshold:
            raise ValueError("result context threshold does not match protocol file")

        if protocol.context_projection_configuration_schema_version is not None:
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
            raise ValueError("formal context experiment contains a dirty MiniCode run")

        if result.input_tokens <= 0:
            raise ValueError(
                "context experiment requires positive Provider input tokens"
            )

        if experiment.model_call_count != result.model_call_count:
            raise ValueError("context and run model-call counts disagree")

        if result.run_id is None:
            raise ValueError("context experiment result must contain a run_id")

        if result.run_id in run_ids:
            raise ValueError(f"duplicate context experiment run_id: {result.run_id}")

        run_ids.add(result.run_id)
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
    advancement_passed = all(
        (
            repetition_complete,
            safe_success_gate,
            aggregate_token_gate,
            per_case_token_gate,
            readback_gate,
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
                "- Safe Task Success: "
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
            f"- Advancement gate: {'PASS' if advancement_passed else 'FAIL'}",
        )
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
    _verify_artifacts(result, path)
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

    return _RecordedEvaluation(
        case_id=_required_string(result, "case_id", path),
        outcome_passed=outcome_passed,
        operational_passed=operational_passed,
        budget_passed=budget_passed,
        trace_passed=trace_passed,
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
        run_id=_optional_string(run, "run_id", path),
        context_experiment=context_experiment,
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
    expected_strategy = "identity" if arm == "baseline" else "tool_result_reference"
    configuration_schema_version = trace_configuration.get(
        "configuration_schema_version"
    )
    recorded_configuration_schema_version: int | None = None
    recorded_minimum_net_savings: int | None = None
    recorded_retrieval_tool_loading: str | None = None

    if _required_string(trace_configuration, "strategy", path) != expected_strategy:
        raise ValueError(f"context trace strategy disagrees with arm: {path}")

    if trace_configuration.get("max_inline_tool_result_bytes") != threshold:
        raise ValueError(f"context trace threshold disagrees with result: {path}")

    if configuration_schema_version is not None:
        if configuration_schema_version != 2:
            raise ValueError(f"unknown context trace configuration schema: {path}")

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
    )


def _verify_artifacts(
    result: Mapping[str, object],
    result_path: Path,
) -> None:
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
    parser.add_argument(
        "--context-protocol",
        type=Path,
        help="Pre-registered context protocol for A/B gate reporting.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print one summary for a recorded evaluation batch."""
    args = build_parser().parse_args(argv)
    if args.context_protocol is None:
        summary = summarize_results(args.results_root)
    else:
        summary = summarize_context_experiment_results(
            args.results_root,
            args.context_protocol,
        )

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
