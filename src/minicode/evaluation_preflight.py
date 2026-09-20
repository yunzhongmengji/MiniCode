"""Coordinate one pre-registered two-arm context Preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from minicode.context_experiment_protocol import (
    BudgetedContextExperimentProtocol,
    load_budgeted_context_experiment_protocol,
)


@dataclass(frozen=True, slots=True)
class PreflightRunRequest:
    """One arm that an execution adapter must run and record."""

    run_index: int
    protocol_snapshot_path: Path
    protocol_id: str
    case_id: str
    arm: str
    result_directory: Path


class PreflightRunExecutor(Protocol):
    """The small boundary between ordering and real command execution."""

    def execute(self, request: PreflightRunRequest) -> bool:
        """Run one arm and return whether its evaluation passed."""


@dataclass(frozen=True, slots=True)
class PreflightRunRecord:
    """The coordinator's verified outcome for one attempted arm."""

    run_index: int
    arm: str
    result_directory: Path
    passed: bool
    result_recorded: bool
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class PreflightOrchestrationResult:
    """The completed prefix of the frozen Preflight plan."""

    results_root: Path
    planned_run_count: int
    records: tuple[PreflightRunRecord, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every planned run completed successfully."""
        return len(self.records) == self.planned_run_count and all(
            record.passed for record in self.records
        )

    @property
    def stopped_early(self) -> bool:
        """Return whether a failed arm prevented later arms from starting."""
        return len(self.records) < self.planned_run_count


@dataclass(frozen=True, slots=True)
class PreflightEvidenceRun:
    """One result slot frozen by the orchestration plan."""

    run_index: int
    arm: str
    result_directory: str
    result_path: Path


@dataclass(frozen=True, slots=True)
class PreflightEvidenceValidation:
    """Cross-file orchestration facts needed by the final gate."""

    runs: tuple[PreflightEvidenceRun, ...]
    event_sequence_passed: bool
    result_path_set_passed: bool

    @property
    def passed(self) -> bool:
        """Return whether events and result locations match the frozen plan."""
        return self.event_sequence_passed and self.result_path_set_passed


def run_budgeted_context_preflight(
    *,
    protocol_path: Path,
    results_root: Path,
    executor: PreflightRunExecutor,
) -> PreflightOrchestrationResult:
    """Run the registered Preflight arms in order and stop at first failure."""
    source_protocol_path = protocol_path.resolve(strict=True)
    protocol = load_budgeted_context_experiment_protocol(source_protocol_path)
    root = _create_new_results_root(results_root)
    snapshot_path = root / "protocol.snapshot.json"
    protocol_bytes = source_protocol_path.read_bytes()
    snapshot_path.write_bytes(protocol_bytes)
    runs = _build_evidence_runs(protocol, root)
    _write_json_exclusively(
        root / "preflight-plan.json",
        _build_plan_payload(protocol, protocol_bytes, runs),
    )

    event_path = root / "preflight-events.jsonl"
    records: list[PreflightRunRecord] = []

    for run in runs:
        run_index = run.run_index
        arm = run.arm
        result_directory = run.result_path.parent
        result_directory.mkdir()
        request = PreflightRunRequest(
            run_index=run_index,
            protocol_snapshot_path=snapshot_path,
            protocol_id=protocol.protocol_id,
            case_id=protocol.preflight_plan.case_id,
            arm=arm,
            result_directory=result_directory,
        )
        event_identity = {
            "run_index": run_index,
            "arm": arm,
            "result_directory": result_directory.name,
        }
        _append_event(
            event_path,
            {"event": "run_started", **event_identity},
        )

        try:
            executor_passed = executor.execute(request)
        except Exception as error:
            _append_event(
                event_path,
                {
                    "event": "run_failed",
                    **event_identity,
                    "failure_reason": "executor_raised",
                    "error_type": type(error).__name__,
                },
            )
            raise

        result_recorded = (result_directory / "result.json").is_file()
        passed = executor_passed and result_recorded
        failure_reason: str | None = None

        if not executor_passed:
            failure_reason = "executor_reported_failure"
        elif not result_recorded:
            failure_reason = "result_json_missing"

        record = PreflightRunRecord(
            run_index=run_index,
            arm=arm,
            result_directory=result_directory,
            passed=passed,
            result_recorded=result_recorded,
            failure_reason=failure_reason,
        )
        records.append(record)
        _append_event(
            event_path,
            {
                "event": "run_finished",
                **event_identity,
                "passed": passed,
                "result_recorded": result_recorded,
                "failure_reason": failure_reason,
            },
        )

        if not passed:
            break

    return PreflightOrchestrationResult(
        results_root=root,
        planned_run_count=len(runs),
        records=tuple(records),
    )


def validate_budgeted_preflight_evidence(
    *,
    results_root: Path,
    protocol_path: Path,
) -> PreflightEvidenceValidation:
    """Validate a schema-three plan, event stream, and result locations."""
    root = results_root.resolve(strict=True)
    source_protocol_path = protocol_path.resolve(strict=True)
    protocol = load_budgeted_context_experiment_protocol(source_protocol_path)
    protocol_bytes = source_protocol_path.read_bytes()
    runs = _build_evidence_runs(protocol, root)
    expected_plan = _build_plan_payload(protocol, protocol_bytes, runs)
    plan_path = root / "preflight-plan.json"
    decoded_plan = _load_json_mapping(plan_path)
    _validate_plan_field_types(decoded_plan, plan_path)

    if dict(decoded_plan) != expected_plan:
        raise ValueError("Preflight plan disagrees with the registered protocol")

    expected_events: list[dict[str, object]] = []

    for run in runs:
        event_identity = {
            "run_index": run.run_index,
            "arm": run.arm,
            "result_directory": run.result_directory,
        }
        expected_events.extend(
            (
                {"event": "run_started", **event_identity},
                {
                    "event": "run_finished",
                    **event_identity,
                    "passed": True,
                    "result_recorded": True,
                    "failure_reason": None,
                },
            )
        )

    events = _load_preflight_events(root / "preflight-events.jsonl")
    expected_result_paths = frozenset(
        run.result_path.relative_to(root) for run in runs
    )
    actual_result_paths = frozenset(
        path.relative_to(root) for path in root.rglob("result.json")
    )
    return PreflightEvidenceValidation(
        runs=runs,
        event_sequence_passed=events == expected_events,
        result_path_set_passed=actual_result_paths == expected_result_paths,
    )


def _build_evidence_runs(
    protocol: BudgetedContextExperimentProtocol,
    root: Path,
) -> tuple[PreflightEvidenceRun, ...]:
    return tuple(
        PreflightEvidenceRun(
            run_index=run_index,
            arm=arm,
            result_directory=f"{run_index:02d}-{arm}",
            result_path=root / f"{run_index:02d}-{arm}" / "result.json",
        )
        for run_index, arm in enumerate(
            protocol.preflight_plan.arm_order,
            start=1,
        )
    )


def _build_plan_payload(
    protocol: BudgetedContextExperimentProtocol,
    protocol_bytes: bytes,
    runs: tuple[PreflightEvidenceRun, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol_id": protocol.protocol_id,
        "protocol_snapshot_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "case_id": protocol.preflight_plan.case_id,
        "runs": [
            {
                "run_index": run.run_index,
                "arm": run.arm,
                "result_directory": run.result_directory,
            }
            for run in runs
        ],
    }


def _create_new_results_root(path: Path) -> Path:
    if path.name in {"", ".", ".."}:
        raise ValueError("Preflight results root must name a new directory")

    path.mkdir()
    return path.resolve(strict=True)


def _write_json_exclusively(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _append_event(path: Path, event: object) -> None:
    with path.open("a", encoding="utf-8") as stream:
        json.dump(event, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"Preflight JSON must be an object: {path}")

    return decoded


def _validate_plan_field_types(
    plan: Mapping[str, object],
    path: Path,
) -> None:
    if set(plan) != {
        "schema_version",
        "protocol_id",
        "protocol_snapshot_sha256",
        "case_id",
        "runs",
    }:
        raise ValueError(f"Preflight plan fields are invalid: {path}")

    if type(plan["schema_version"]) is not int:
        raise TypeError(f"Preflight plan schema_version must be an integer: {path}")

    for field in ("protocol_id", "protocol_snapshot_sha256", "case_id"):
        if not isinstance(plan[field], str):
            raise TypeError(f"Preflight plan {field} must be a string: {path}")

    run_payloads = plan["runs"]

    if not isinstance(run_payloads, list):
        raise TypeError(f"Preflight plan runs must be a list: {path}")

    for run in run_payloads:
        if not isinstance(run, Mapping) or set(run) != {
            "run_index",
            "arm",
            "result_directory",
        }:
            raise ValueError(f"Preflight plan run fields are invalid: {path}")

        if type(run["run_index"]) is not int:
            raise TypeError(f"Preflight plan run_index must be an integer: {path}")

        if not isinstance(run["arm"], str) or not isinstance(
            run["result_directory"], str
        ):
            raise TypeError(f"Preflight plan run strings are invalid: {path}")


def _load_preflight_events(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []

    events: list[dict[str, object]] = []

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        decoded: object = json.loads(line)

        if not isinstance(decoded, Mapping):
            raise TypeError(
                f"Preflight event must be an object: {path}:{line_number}"
            )

        event = dict(decoded)
        _validate_event_field_types(event, path, line_number)
        events.append(event)

    return events


def _validate_event_field_types(
    event: Mapping[str, object],
    path: Path,
    line_number: int,
) -> None:
    location = f"{path}:{line_number}"
    event_name = event.get("event")
    common_fields = {"event", "run_index", "arm", "result_directory"}

    if event_name == "run_started":
        expected_fields = common_fields
    elif event_name == "run_finished":
        expected_fields = common_fields | {
            "passed",
            "result_recorded",
            "failure_reason",
        }
    elif event_name == "run_failed":
        expected_fields = common_fields | {"failure_reason", "error_type"}
    else:
        raise ValueError(f"unknown Preflight event at {location}")

    if set(event) != expected_fields:
        raise ValueError(f"Preflight event fields are invalid at {location}")

    if type(event["run_index"]) is not int:
        raise TypeError(f"Preflight event run_index must be an integer at {location}")

    if not isinstance(event["arm"], str) or not isinstance(
        event["result_directory"], str
    ):
        raise TypeError(f"Preflight event identity is invalid at {location}")

    if event_name == "run_finished":
        if type(event["passed"]) is not bool or type(
            event["result_recorded"]
        ) is not bool:
            raise TypeError(f"Preflight event outcomes are invalid at {location}")

        if event["failure_reason"] is not None and not isinstance(
            event["failure_reason"], str
        ):
            raise TypeError(f"Preflight failure_reason is invalid at {location}")

    if event_name == "run_failed" and (
        not isinstance(event["failure_reason"], str)
        or not isinstance(event["error_type"], str)
    ):
        raise TypeError(f"Preflight failure event is invalid at {location}")


def build_parser() -> argparse.ArgumentParser:
    """Build the registered Preflight batch argument parser."""
    parser = argparse.ArgumentParser(
        description="Run one registered MiniCode context Preflight batch.",
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--temporary-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run, record, and gate one registered two-arm Preflight batch."""
    args = build_parser().parse_args(argv)

    from minicode.evaluation_preflight_executor import (
        ContextPreflightCommandExecutor,
    )
    from minicode.evaluation_summary import summarize_context_preflight_results

    try:
        executor = ContextPreflightCommandExecutor(
            project_root=args.project_root,
            temporary_root=args.temporary_root,
        )
        executor.validate_environment(args.results_root)
        result = run_budgeted_context_preflight(
            protocol_path=args.protocol,
            results_root=args.results_root,
            executor=executor,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Preflight error: {error}", file=sys.stderr)
        return 2

    if not result.passed:
        print(
            f"Preflight execution failed after {len(result.records)}/"
            f"{result.planned_run_count} runs: {result.results_root}",
            file=sys.stderr,
        )
        return 1

    try:
        summary = summarize_context_preflight_results(
            result.results_root,
            args.protocol,
        )
    except (OSError, TypeError, ValueError) as error:
        print(f"Preflight gate error: {error}", file=sys.stderr)
        return 2

    print(summary)
    return 1 if summary.endswith("- Preflight gate: FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
