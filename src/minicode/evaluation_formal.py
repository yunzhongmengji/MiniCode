"""Coordinate the frozen sample order for one formal context experiment."""

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
from typing import Protocol, cast

from minicode.context_experiment_protocol import (
    BudgetedContextExperimentProtocol,
    ContextExperimentBudget,
    load_budgeted_context_experiment_protocol,
)


@dataclass(frozen=True, slots=True)
class FormalRunRequest:
    """One immutable sample in the pre-registered formal schedule."""

    run_index: int
    protocol_snapshot_path: Path
    protocol_id: str
    case_id: str
    arm: str
    result_directory: Path


class FormalRunExecutor(Protocol):
    """Execute one formal sample through a replaceable command boundary."""

    def execute(self, request: FormalRunRequest) -> bool:
        """Run and record one sample; return whether the task itself passed."""


@dataclass(frozen=True, slots=True)
class FormalRunRecord:
    """The observed outcome of one attempted formal sample."""

    request: FormalRunRequest
    task_passed: bool
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class FormalOrchestrationResult:
    """The completed prefix of the frozen formal schedule."""

    results_root: Path
    planned_run_count: int
    records: tuple[FormalRunRecord, ...]
    budget: ContextExperimentBudget
    stop_reason: str | None

    @property
    def execution_complete(self) -> bool:
        """Return whether every registered sample produced a result record."""
        return len(self.records) == self.planned_run_count

    @property
    def input_tokens(self) -> int:
        """Return cumulative provider input tokens for recorded samples."""
        return sum(record.input_tokens for record in self.records)

    @property
    def output_tokens(self) -> int:
        """Return cumulative provider output tokens for recorded samples."""
        return sum(record.output_tokens for record in self.records)

    @property
    def budget_within_limits(self) -> bool:
        """Return whether the recorded prefix remains inside frozen limits."""
        return (
            len(self.records) <= self.budget.maximum_runs
            and self.input_tokens <= self.budget.maximum_input_tokens
            and self.output_tokens <= self.budget.maximum_output_tokens
        )


@dataclass(frozen=True, slots=True)
class FormalEvidenceRun:
    """One result slot frozen by the formal orchestration plan."""

    run_index: int
    case_id: str
    arm: str
    result_directory: str
    result_path: Path


@dataclass(frozen=True, slots=True)
class FormalEvidenceValidation:
    """Cross-file evidence required before formal metrics are trusted."""

    runs: tuple[FormalEvidenceRun, ...]
    protocol_snapshot_passed: bool
    event_sequence_passed: bool
    result_path_set_passed: bool

    @property
    def passed(self) -> bool:
        """Return whether snapshot, events, and result slots all agree."""
        return (
            self.protocol_snapshot_passed
            and self.event_sequence_passed
            and self.result_path_set_passed
        )


def run_budgeted_context_formal_experiment(
    *,
    protocol_path: Path,
    results_root: Path,
    executor: FormalRunExecutor,
) -> FormalOrchestrationResult:
    """Execute formal samples in frozen order without replacing failed tasks."""
    source_protocol_path = protocol_path.resolve(strict=True)
    protocol = load_budgeted_context_experiment_protocol(source_protocol_path)
    root = _create_new_results_root(results_root)
    protocol_bytes = source_protocol_path.read_bytes()
    snapshot_path = root / "protocol.snapshot.json"
    snapshot_path.write_bytes(protocol_bytes)
    requests = _build_run_requests(protocol, root, snapshot_path)
    _write_json_exclusively(
        root / "formal-plan.json",
        _build_plan_payload(protocol, protocol_bytes, requests),
    )

    event_path = root / "formal-events.jsonl"
    records: list[FormalRunRecord] = []
    stop_reason: str | None = None

    for request in requests:
        request.result_directory.mkdir()
        identity = _event_identity(request)
        _append_event(event_path, {"event": "run_started", **identity})

        try:
            task_passed = executor.execute(request)
        except Exception as error:
            _append_event(
                event_path,
                {
                    "event": "run_failed",
                    **identity,
                    "failure_reason": "executor_raised",
                    "error_type": type(error).__name__,
                },
            )
            raise

        result_path = request.result_directory / "result.json"

        if not result_path.is_file():
            stop_reason = "result_json_missing"
            _append_event(
                event_path,
                {
                    "event": "run_failed",
                    **identity,
                    "failure_reason": stop_reason,
                    "error_type": None,
                },
            )
            break

        try:
            input_tokens, output_tokens = _read_recorded_usage(result_path)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            stop_reason = "result_usage_invalid"
            _append_event(
                event_path,
                {
                    "event": "run_failed",
                    **identity,
                    "failure_reason": stop_reason,
                    "error_type": type(error).__name__,
                },
            )
            break

        records.append(
            FormalRunRecord(
                request=request,
                task_passed=task_passed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )
        cumulative_input_tokens = sum(record.input_tokens for record in records)
        cumulative_output_tokens = sum(record.output_tokens for record in records)
        budget_exceeded = (
            cumulative_input_tokens > protocol.formal_budget.maximum_input_tokens
            or cumulative_output_tokens
            > protocol.formal_budget.maximum_output_tokens
        )
        _append_event(
            event_path,
            {
                "event": "run_finished",
                **identity,
                "task_passed": task_passed,
                "result_recorded": True,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cumulative_input_tokens": cumulative_input_tokens,
                "cumulative_output_tokens": cumulative_output_tokens,
                "budget_exceeded": budget_exceeded,
            },
        )

        if budget_exceeded:
            stop_reason = "formal_budget_exceeded"
            break

    return FormalOrchestrationResult(
        results_root=root,
        planned_run_count=len(requests),
        records=tuple(records),
        budget=protocol.formal_budget,
        stop_reason=stop_reason,
    )


def validate_budgeted_formal_evidence(
    *,
    results_root: Path,
    protocol_path: Path,
) -> FormalEvidenceValidation:
    """Verify one formal plan, event stream, snapshot, and result path set."""
    root = results_root.resolve(strict=True)
    source_protocol_path = protocol_path.resolve(strict=True)
    protocol = load_budgeted_context_experiment_protocol(source_protocol_path)
    protocol_bytes = source_protocol_path.read_bytes()
    snapshot_path = root / "protocol.snapshot.json"
    requests = _build_run_requests(protocol, root, snapshot_path)
    expected_plan = _build_plan_payload(protocol, protocol_bytes, requests)
    decoded_plan = _load_json_mapping(root / "formal-plan.json")

    if dict(decoded_plan) != expected_plan:
        raise ValueError("Formal plan disagrees with the registered protocol")

    runs = tuple(
        FormalEvidenceRun(
            run_index=request.run_index,
            case_id=request.case_id,
            arm=request.arm,
            result_directory=request.result_directory.name,
            result_path=request.result_directory / "result.json",
        )
        for request in requests
    )
    expected_result_paths = frozenset(
        run.result_path.relative_to(root) for run in runs
    )
    actual_result_paths = frozenset(
        path.relative_to(root) for path in root.rglob("result.json")
    )
    result_path_set_passed = actual_result_paths == expected_result_paths
    protocol_snapshot_passed = (
        snapshot_path.is_file() and snapshot_path.read_bytes() == protocol_bytes
    )
    event_sequence_passed = False

    if result_path_set_passed:
        expected_events: list[dict[str, object]] = []
        cumulative_input_tokens = 0
        cumulative_output_tokens = 0

        for request in requests:
            input_tokens, output_tokens = _read_recorded_usage(
                request.result_directory / "result.json"
            )
            task_passed = _read_recorded_task_passed(
                request.result_directory / "result.json"
            )
            cumulative_input_tokens += input_tokens
            cumulative_output_tokens += output_tokens
            budget_exceeded = (
                cumulative_input_tokens
                > protocol.formal_budget.maximum_input_tokens
                or cumulative_output_tokens
                > protocol.formal_budget.maximum_output_tokens
            )
            identity = _event_identity(request)
            expected_events.extend(
                (
                    {"event": "run_started", **identity},
                    {
                        "event": "run_finished",
                        **identity,
                        "task_passed": task_passed,
                        "result_recorded": True,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cumulative_input_tokens": cumulative_input_tokens,
                        "cumulative_output_tokens": cumulative_output_tokens,
                        "budget_exceeded": budget_exceeded,
                    },
                )
            )

        event_sequence_passed = _load_events(
            root / "formal-events.jsonl"
        ) == expected_events

    return FormalEvidenceValidation(
        runs=runs,
        protocol_snapshot_passed=protocol_snapshot_passed,
        event_sequence_passed=event_sequence_passed,
        result_path_set_passed=result_path_set_passed,
    )


def _build_run_requests(
    protocol: BudgetedContextExperimentProtocol,
    root: Path,
    snapshot_path: Path,
) -> tuple[FormalRunRequest, ...]:
    requests: list[FormalRunRequest] = []

    for case_id in protocol.cases:
        for arm in protocol.paired_arm_order_per_case:
            run_index = len(requests) + 1
            directory_name = f"{run_index:02d}-{case_id}-{arm}"
            requests.append(
                FormalRunRequest(
                    run_index=run_index,
                    protocol_snapshot_path=snapshot_path,
                    protocol_id=protocol.protocol_id,
                    case_id=case_id,
                    arm=arm,
                    result_directory=root / directory_name,
                )
            )

    if len(requests) != protocol.formal_budget.maximum_runs:
        raise ValueError("formal schedule disagrees with maximum run budget")

    return tuple(requests)


def _build_plan_payload(
    protocol: BudgetedContextExperimentProtocol,
    protocol_bytes: bytes,
    requests: tuple[FormalRunRequest, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol_id": protocol.protocol_id,
        "protocol_snapshot_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "budget": {
            "maximum_runs": protocol.formal_budget.maximum_runs,
            "maximum_input_tokens": protocol.formal_budget.maximum_input_tokens,
            "maximum_output_tokens": protocol.formal_budget.maximum_output_tokens,
        },
        "runs": [
            {
                "run_index": request.run_index,
                "case_id": request.case_id,
                "arm": request.arm,
                "result_directory": request.result_directory.name,
            }
            for request in requests
        ],
    }


def _read_recorded_usage(path: Path) -> tuple[int, int]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError("formal result must be a JSON object")

    result = cast(Mapping[str, object], decoded)
    run = result["run"]

    if not isinstance(run, Mapping):
        raise TypeError("formal result run must be a JSON object")

    input_tokens = run.get("input_tokens")
    output_tokens = run.get("output_tokens")

    if type(input_tokens) is not int or type(output_tokens) is not int:
        raise TypeError("formal result token usage must contain integers")

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("formal result token usage must not be negative")

    return input_tokens, output_tokens


def _read_recorded_task_passed(path: Path) -> bool:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError("formal result must be a JSON object")

    result = cast(Mapping[str, object], decoded)
    verdict = result.get("verdict")

    if not isinstance(verdict, Mapping):
        raise TypeError("formal result verdict must be a JSON object")

    passed = verdict.get("passed")

    if type(passed) is not bool:
        raise TypeError("formal result verdict passed must be a boolean")

    return passed


def _event_identity(request: FormalRunRequest) -> dict[str, object]:
    return {
        "run_index": request.run_index,
        "case_id": request.case_id,
        "arm": request.arm,
        "result_directory": request.result_directory.name,
    }


def _create_new_results_root(path: Path) -> Path:
    if path.name in {"", ".", ".."}:
        raise ValueError("formal results root must name a new directory")

    path.mkdir()
    return path.resolve(strict=True)


def _write_json_exclusively(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"Formal JSON must be an object: {path}")

    return decoded


def _load_events(path: Path) -> list[dict[str, object]]:
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
                f"Formal event must be an object: {path}:{line_number}"
            )

        events.append(dict(decoded))

    return events


def _append_event(path: Path, event: object) -> None:
    with path.open("a", encoding="utf-8") as stream:
        json.dump(event, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_parser() -> argparse.ArgumentParser:
    """Build the registered formal-experiment batch argument parser."""
    parser = argparse.ArgumentParser(
        description="Run one registered MiniCode formal context experiment.",
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--temporary-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run, record, and gate one registered formal context batch."""
    args = build_parser().parse_args(argv)

    from minicode import evaluation_archive as archive_module
    from minicode.evaluation_preflight_executor import (
        ContextFormalCommandExecutor,
    )
    from minicode.evaluation_summary import summarize_context_experiment_results

    try:
        executor = ContextFormalCommandExecutor(
            project_root=args.project_root,
            temporary_root=args.temporary_root,
        )
        executor.validate_environment(args.results_root)
        archive_module.validate_formal_archive_target(
            archive_root=args.archive_root,
            source_root=args.results_root,
        )
        result = run_budgeted_context_formal_experiment(
            protocol_path=args.protocol,
            results_root=args.results_root,
            executor=executor,
        )
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Formal experiment error: {error}", file=sys.stderr)
        return 2

    if not result.execution_complete:
        print(
            "Formal experiment stopped after "
            f"{len(result.records)}/{result.planned_run_count} recorded samples: "
            f"{result.stop_reason}",
            file=sys.stderr,
        )
        return 1

    try:
        summary = summarize_context_experiment_results(
            result.results_root,
            args.protocol,
        )
        archive = archive_module.archive_formal_experiment(
            source_root=result.results_root,
            archive_root=args.archive_root,
            protocol_path=args.protocol,
        )
    except (OSError, TypeError, ValueError) as error:
        print(f"Formal experiment gate error: {error}", file=sys.stderr)
        return 2

    if archive.summary != summary:
        print(
            "Formal experiment gate error: archive summary changed after return",
            file=sys.stderr,
        )
        return 2

    print(summary)
    print(f"Formal archive: {archive.archive_root}")
    return 1 if summary.endswith("- Advancement gate: FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
