"""Record one completed Coding Agent evaluation as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from minicode.context_experiment_protocol import (
    BudgetedContextExperimentProtocol,
    load_budgeted_context_experiment_protocol,
)
from minicode.context_trace import ContextTraceMetrics, summarize_context_trace
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)
from minicode.core.events import EventKind, LedgerEvent
from minicode.core.replay import RunReplay
from minicode.core.tool_calls import JsonValue
from minicode.evaluation_case import (
    EvaluationBudget,
    load_case_manifest,
)
from minicode.evaluation_run import EvaluationArm, context_threshold_for_arm
from minicode.evaluation_trace import (
    TraceEvaluation,
    evaluate_trace_expectations,
)


def parse_trace(trace: str) -> RunReplay:
    """Parse CLI trace text into the existing validated replay model."""
    lines = tuple(line for line in trace.splitlines() if line)
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("Trace ")),
        None,
    )

    if header_index is None:
        raise ValueError("trace must contain a 'Trace RUN_ID' header")

    run_id = lines[header_index].removeprefix("Trace ")
    events: list[LedgerEvent] = []

    for line in lines[header_index + 1 :]:
        parts = line.split(
            " ",
            2,
        )

        if len(parts) != 3:
            raise ValueError(f"invalid trace event line: {line}")

        sequence_text, kind_text, payload_text = parts
        decoded_payload: object = json.loads(payload_text)

        if not isinstance(decoded_payload, Mapping):
            raise TypeError("trace event payload must be an object")

        events.append(
            LedgerEvent(
                run_id=run_id,
                sequence=int(sequence_text),
                kind=EventKind(kind_text),
                payload=cast(
                    Mapping[str, JsonValue],
                    decoded_payload,
                ),
            )
        )

    return RunReplay(events=events)


def summarize_trace(replay: RunReplay) -> dict[str, object]:
    """Return stable counts and outcomes from a validated replay."""
    input_tokens = 0
    output_tokens = 0
    tool_requests: Counter[str] = Counter()

    for event in replay.events:
        if event.kind is EventKind.MODEL_CALL_FINISHED:
            input_tokens += _optional_integer(event, "input_tokens")
            output_tokens += _optional_integer(event, "output_tokens")

        if event.kind is EventKind.TOOL_POLICY_DECIDED:
            tool_name = event.payload.get("tool_name")

            if not isinstance(tool_name, str):
                raise TypeError("tool policy event must contain a string tool_name")

            tool_requests[tool_name] += 1

    final_payload = replay.events[-1].payload if replay.is_finished else {}

    return {
        "run_id": replay.run_id,
        "outcome": replay.outcome,
        "stop_reason": final_payload.get("stop_reason"),
        "turns_used": final_payload.get("turns_used"),
        "model_call_count": replay.model_call_count,
        "tool_execution_count": replay.tool_execution_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_requests": dict(sorted(tool_requests.items())),
    }


def summarize_context_experiment(
    replay: RunReplay,
    *,
    protocol_id: str,
    arm: EvaluationArm,
) -> dict[str, object]:
    """Validate declared context configuration and aggregate Trace facts."""
    if not isinstance(protocol_id, str):
        raise TypeError("context protocol_id must be a string")

    if not protocol_id.strip():
        raise ValueError("context protocol_id must not be blank")

    if not isinstance(arm, EvaluationArm):
        raise TypeError("context arm must be an EvaluationArm")

    expected_threshold = context_threshold_for_arm(arm)
    expected_strategy = (
        "identity" if arm is EvaluationArm.BASELINE else "tool_result_reference"
    )
    expected_minimum_net_savings = None if arm is EvaluationArm.BASELINE else 1
    expected_retrieval_tool_loading = (
        None if arm is EvaluationArm.BASELINE else "on_reference"
    )
    for event in replay.events:
        if event.kind is EventKind.MODEL_CALL_STARTED:
            projection = _required_event_mapping(event, "context_projection")
            configuration_schema_version = projection.get(
                "configuration_schema_version"
            )
            strategy = projection.get("strategy")
            threshold = projection.get("max_inline_tool_result_bytes")
            minimum_net_savings = projection.get("minimum_net_savings_bytes")
            retrieval_tool_loading = projection.get("retrieval_tool_loading")

            required_configuration_fields = (
                "configuration_schema_version",
                "strategy",
                "max_inline_tool_result_bytes",
                "minimum_net_savings_bytes",
                "retrieval_tool_loading",
            )
            missing_configuration_fields = tuple(
                field
                for field in required_configuration_fields
                if field not in projection
            )

            if missing_configuration_fields:
                raise ValueError(
                    "context projection configuration is missing fields: "
                    + ", ".join(missing_configuration_fields)
                )

            if configuration_schema_version != 2:
                raise ValueError("unknown context projection configuration schema")

            if not isinstance(strategy, str):
                raise TypeError("context projection strategy must be a string")

            if threshold is not None and type(threshold) is not int:
                raise TypeError(
                    "max_inline_tool_result_bytes must be an integer or null"
                )

            if minimum_net_savings is not None and type(minimum_net_savings) is not int:
                raise TypeError("minimum_net_savings_bytes must be an integer or null")

            if retrieval_tool_loading is not None and not isinstance(
                retrieval_tool_loading, str
            ):
                raise TypeError("retrieval_tool_loading must be a string or null")

            if (
                strategy != expected_strategy
                or threshold != expected_threshold
                or minimum_net_savings != expected_minimum_net_savings
                or retrieval_tool_loading != expected_retrieval_tool_loading
            ):
                raise ValueError(
                    f"declared context arm {arm.value} disagrees with Trace "
                    "configuration "
                    f"{strategy}/{threshold}/{minimum_net_savings}/"
                    f"{retrieval_tool_loading}"
                )

    metrics = summarize_context_trace(replay.events)

    if metrics.model_call_count == 0:
        raise ValueError("context experiment Trace has no model calls")

    if arm is EvaluationArm.BASELINE and (
        metrics.projection_bytes_saved != 0
        or metrics.changed_tool_result_count != 0
        or metrics.successful_readback_count != 0
        or metrics.failed_readback_count != 0
        or metrics.cancelled_readback_count != 0
    ):
        raise ValueError("baseline Trace contains projection or readback activity")

    return {
        "protocol_id": protocol_id,
        "arm": arm,
        "max_inline_tool_result_bytes": expected_threshold,
        "trace_configuration": {
            "configuration_schema_version": 2,
            "strategy": expected_strategy,
            "max_inline_tool_result_bytes": expected_threshold,
            "minimum_net_savings_bytes": expected_minimum_net_savings,
            "retrieval_tool_loading": expected_retrieval_tool_loading,
        },
        "metrics": _context_metrics_payload(metrics),
    }


def summarize_budgeted_context_experiment(
    replay: RunReplay,
    *,
    protocol_id: str,
    expected_configuration: BudgetedContextProjectionConfiguration,
) -> dict[str, object]:
    """Validate one schema-three projection Trace without changing v3 rules."""
    if not isinstance(protocol_id, str):
        raise TypeError("context protocol_id must be a string")

    if not protocol_id.strip():
        raise ValueError("context protocol_id must not be blank")

    if not isinstance(
        expected_configuration,
        BudgetedContextProjectionConfiguration,
    ):
        raise TypeError(
            "expected_configuration must be a "
            "BudgetedContextProjectionConfiguration"
        )

    recorded_configuration: BudgetedContextProjectionConfiguration | None = None

    for event in replay.events:
        if event.kind is not EventKind.MODEL_CALL_STARTED:
            continue

        projection = _required_event_mapping(event, "context_projection")
        current_configuration = _budgeted_configuration_from_trace(projection)

        if (
            recorded_configuration is not None
            and current_configuration != recorded_configuration
        ):
            raise ValueError(
                "budgeted context Trace configuration changed between model calls"
            )

        if current_configuration != expected_configuration:
            raise ValueError(
                "budgeted context Trace configuration disagrees with the "
                "registered protocol"
            )

        recorded_configuration = current_configuration

    metrics = summarize_context_trace(replay.events)

    if metrics.model_call_count == 0:
        raise ValueError("context experiment Trace has no model calls")

    return {
        "protocol_id": protocol_id,
        "arm": EvaluationArm.PROJECTION,
        "max_request_bytes": expected_configuration.max_request_bytes,
        "trace_configuration": expected_configuration.to_payload(),
        "metrics": _context_metrics_payload(metrics),
    }


def summarize_registered_context_experiment(
    replay: RunReplay,
    *,
    protocol: BudgetedContextExperimentProtocol,
    arm: EvaluationArm,
    case_id: str,
    model: str,
) -> dict[str, object]:
    """Validate one run against the complete pre-registered v4 protocol."""
    if case_id not in protocol.cases:
        raise ValueError(
            f"case {case_id} is not registered by protocol {protocol.protocol_id}"
        )

    if model != protocol.model.name:
        raise ValueError(
            "result model does not match the registered context protocol"
        )

    if arm is EvaluationArm.BASELINE:
        return summarize_context_experiment(
            replay,
            protocol_id=protocol.protocol_id,
            arm=arm,
        )

    return summarize_budgeted_context_experiment(
        replay,
        protocol_id=protocol.protocol_id,
        expected_configuration=protocol.projection_configuration,
    )


def _budgeted_configuration_from_trace(
    projection: Mapping[str, object],
) -> BudgetedContextProjectionConfiguration:
    configuration_fields = (
        "configuration_schema_version",
        "strategy",
        "max_request_bytes",
        "protected_recent_batch_count",
        "minimum_net_savings_bytes",
        "excluded_tool_names",
        "max_retrievable_output_bytes",
        "retrieval_tool_loading",
    )
    missing_fields = tuple(
        field for field in configuration_fields if field not in projection
    )

    if missing_fields:
        raise ValueError(
            "budgeted context projection configuration is missing fields: "
            + ", ".join(missing_fields)
        )

    configuration_payload = {
        field: projection[field] for field in configuration_fields
    }
    return BudgetedContextProjectionConfiguration.from_payload(
        configuration_payload
    )


def _context_metrics_payload(metrics: ContextTraceMetrics) -> dict[str, int]:
    return {
        "model_call_count": metrics.model_call_count,
        "model_visible_bytes": metrics.model_visible_bytes,
        "canonical_bytes": metrics.canonical_bytes,
        "projection_bytes_saved": metrics.projection_bytes_saved,
        "changed_tool_result_count": metrics.changed_tool_result_count,
        "successful_readback_count": metrics.successful_readback_count,
        "failed_readback_count": metrics.failed_readback_count,
        "cancelled_readback_count": metrics.cancelled_readback_count,
    }


def build_evaluation_verdict(
    *,
    replay: RunReplay,
    acceptance_exit_code: int,
    agent_exit_code: int,
    budget: EvaluationBudget,
    trace_evaluation: TraceEvaluation,
) -> dict[str, bool]:
    """Combine result, operational, budget, and trace checks."""
    final_payload = replay.events[-1].payload if replay.is_finished else {}
    stop_reason = final_payload.get("stop_reason")
    turns_used = final_payload.get("turns_used")
    tool_calls_used = sum(
        _optional_integer(event, "tool_call_count")
        for event in replay.events
        if event.kind is EventKind.MODEL_CALL_FINISHED
    )
    outcome_passed = acceptance_exit_code == 0
    operational_passed = (
        agent_exit_code == 0
        and replay.outcome == "succeeded"
        and stop_reason == "completed"
    )
    budget_passed = (
        type(turns_used) is int
        and turns_used <= budget.max_turns
        and tool_calls_used <= budget.max_tool_calls
    )

    return {
        "outcome_passed": outcome_passed,
        "operational_passed": operational_passed,
        "budget_passed": budget_passed,
        "trace_passed": trace_evaluation.passed,
        "passed": (
            outcome_passed
            and operational_passed
            and budget_passed
            and trace_evaluation.passed
        ),
    }


def record_result(
    *,
    case_root: Path,
    workspace: Path,
    answer_path: Path,
    trace_path: Path,
    output_path: Path,
    model: str,
    agent_exit_code: int,
    context_protocol_id: str | None = None,
    context_arm: EvaluationArm | None = None,
    registered_context_protocol: BudgetedContextExperimentProtocol | None = None,
) -> bool:
    """Run acceptance and write one non-overwriting result document."""
    resolved_case_root = case_root.resolve(strict=True)
    resolved_workspace = workspace.resolve(strict=True)
    resolved_answer = answer_path.resolve(strict=True)
    resolved_trace = trace_path.resolve(strict=True)
    resolved_output = output_path.resolve(strict=False)
    case_manifest = load_case_manifest(resolved_case_root)

    if not model.strip():
        raise ValueError("model must not be blank")

    if context_protocol_id is not None and registered_context_protocol is not None:
        raise ValueError(
            "context protocol_id and registered_context_protocol are mutually "
            "exclusive"
        )

    has_context_protocol = (
        context_protocol_id is not None or registered_context_protocol is not None
    )

    if has_context_protocol != (context_arm is not None):
        raise ValueError("one context protocol and arm must be provided together")

    if resolved_answer.parent != resolved_output.parent:
        raise ValueError("answer and result JSON must share one directory")

    if resolved_trace.parent != resolved_output.parent:
        raise ValueError("trace and result JSON must share one directory")

    patch_path = resolved_output.parent / "workspace.patch"

    for result_artifact in (
        resolved_output,
        patch_path,
    ):
        if result_artifact.exists():
            raise FileExistsError(result_artifact)

    trace = resolved_trace.read_text(encoding="utf-8")
    replay = parse_trace(trace)
    if registered_context_protocol is not None:
        assert context_arm is not None
        context_experiment = summarize_registered_context_experiment(
            replay,
            protocol=registered_context_protocol,
            arm=context_arm,
            case_id=case_manifest.case_id,
            model=model,
        )
    elif context_protocol_id is not None:
        assert context_arm is not None
        context_experiment = summarize_context_experiment(
            replay,
            protocol_id=context_protocol_id,
            arm=context_arm,
        )
    else:
        context_experiment = None
    trace_evaluation = evaluate_trace_expectations(
        replay=replay,
        expectations=case_manifest.trace_expectations,
    )
    workspace_patch = _build_workspace_patch(resolved_workspace)
    acceptance = subprocess.run(
        (
            sys.executable,
            str(resolved_case_root / "acceptance.py"),
            str(resolved_workspace),
            str(resolved_answer),
            str(resolved_trace),
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    verdict = build_evaluation_verdict(
        replay=replay,
        acceptance_exit_code=acceptance.returncode,
        agent_exit_code=agent_exit_code,
        budget=case_manifest.budget,
        trace_evaluation=trace_evaluation,
    )
    project_root = Path(__file__).resolve().parents[2]
    result = {
        "schema_version": 2,
        "case_id": case_manifest.case_id,
        "case_manifest": case_manifest.model_dump(
            mode="json",
        ),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "model": model,
        "minicode_commit": _git_stdout(
            project_root,
            ("rev-parse", "HEAD"),
        ),
        "minicode_dirty": bool(
            _git_stdout(
                project_root,
                ("status", "--short"),
            )
        ),
        "agent_exit_code": agent_exit_code,
        "accepted": acceptance.returncode == 0,
        "verdict": verdict,
        "trace_evaluation": {
            "missing_required_tools": trace_evaluation.missing_required_tools,
            "requested_forbidden_tools": trace_evaluation.requested_forbidden_tools,
            "successful_test_after_last_change": (
                trace_evaluation.successful_test_after_last_change
            ),
        },
        "acceptance": {
            "exit_code": acceptance.returncode,
            "stdout": acceptance.stdout.strip(),
            "stderr": acceptance.stderr.strip(),
        },
        "run": summarize_trace(replay),
        "workspace_status": _git_stdout(
            resolved_workspace,
            (
                "status",
                "--short",
                "--untracked-files=all",
            ),
        ).splitlines(),
        "artifacts": {
            "answer": {
                "file": resolved_answer.name,
                "sha256": _sha256(resolved_answer),
            },
            "trace": {
                "file": resolved_trace.name,
                "sha256": _sha256(resolved_trace),
            },
            "workspace_patch": {
                "file": patch_path.name,
                "sha256": _sha256_bytes(workspace_patch.encode("utf-8")),
            },
        },
    }

    if context_experiment is not None:
        result["context_experiment"] = context_experiment

    resolved_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with patch_path.open(
        "x",
        encoding="utf-8",
    ) as patch_file:
        patch_file.write(workspace_patch)

    with resolved_output.open(
        "x",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            result,
            output_file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        output_file.write("\n")

    return verdict["passed"]


def _optional_integer(
    event: LedgerEvent,
    key: str,
) -> int:
    value = event.payload.get(key)

    if value is None:
        return 0

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer when present")

    return value


def _required_event_mapping(
    event: LedgerEvent,
    key: str,
) -> Mapping[str, object]:
    value = event.payload.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")

    return cast(Mapping[str, object], value)


def _required_mapping_integer(
    source: Mapping[str, object],
    key: str,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer")

    return value


def _git_stdout(
    repository: Path,
    arguments: Sequence[str],
    *,
    strip: bool = True,
) -> str:
    result = subprocess.run(
        (
            "git",
            *arguments,
        ),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip() if strip else result.stdout


def _build_workspace_patch(workspace: Path) -> str:
    tracked_patch = _git_stdout(
        workspace,
        (
            "--literal-pathspecs",
            "--no-pager",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "HEAD",
            "--",
            ".",
        ),
        strip=False,
    )
    untracked_paths = _git_stdout(
        workspace,
        (
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ),
        strip=False,
    ).split("\0")
    patch_parts = [tracked_patch]

    for relative_path in untracked_paths:
        if not relative_path:
            continue

        result = subprocess.run(
            (
                "git",
                "--literal-pathspecs",
                "--no-pager",
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--no-index",
                "--",
                "/dev/null",
                relative_path,
            ),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode not in (0, 1):
            result.check_returncode()

        patch_parts.append(result.stdout)

    return "".join(patch_parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(
            lambda: source.read(65_536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    """Build the result-recorder argument parser."""
    parser = argparse.ArgumentParser(
        description="Record one completed MiniCode evaluation.",
    )
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent-exit-code", type=int, required=True)
    context_protocol = parser.add_mutually_exclusive_group()
    context_protocol.add_argument("--context-protocol-id")
    context_protocol.add_argument("--context-protocol", type=Path)
    parser.add_argument(
        "--context-arm", type=EvaluationArm, choices=tuple(EvaluationArm)
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Record a result and report its acceptance outcome."""
    parser = build_parser()
    args = parser.parse_args(argv)

    has_context_protocol = (
        args.context_protocol_id is not None or args.context_protocol is not None
    )

    if has_context_protocol != (args.context_arm is not None):
        parser.error(
            "one context protocol option and --context-arm must be provided together"
        )

    registered_protocol = (
        load_budgeted_context_experiment_protocol(args.context_protocol)
        if args.context_protocol is not None
        else None
    )

    accepted = record_result(
        case_root=args.case_root,
        workspace=args.workspace,
        answer_path=args.answer,
        trace_path=args.trace,
        output_path=args.output,
        model=args.model,
        agent_exit_code=args.agent_exit_code,
        context_protocol_id=args.context_protocol_id,
        context_arm=args.context_arm,
        registered_context_protocol=registered_protocol,
    )
    print(f"{'PASS' if accepted else 'FAIL'} {args.case_root.name}: {args.output}")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
