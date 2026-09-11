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

from minicode.core.events import EventKind, LedgerEvent
from minicode.core.replay import RunReplay
from minicode.core.tool_calls import JsonValue
from minicode.evaluation_case import (
    EvaluationBudget,
    load_case_manifest,
)
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

    if resolved_answer.parent != resolved_output.parent:
        raise ValueError("answer and result JSON must share one directory")

    if resolved_trace.parent != resolved_output.parent:
        raise ValueError("trace and result JSON must share one directory")

    trace = resolved_trace.read_text(encoding="utf-8")
    replay = parse_trace(trace)
    trace_evaluation = evaluate_trace_expectations(
        replay=replay,
        expectations=case_manifest.trace_expectations,
    )
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
        },
    }

    resolved_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def _git_stdout(
    repository: Path,
    arguments: Sequence[str],
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
    return result.stdout.rstrip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(
            lambda: source.read(65_536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Record a result and report its acceptance outcome."""
    args = build_parser().parse_args(argv)
    accepted = record_result(
        case_root=args.case_root,
        workspace=args.workspace,
        answer_path=args.answer,
        trace_path=args.trace,
        output_path=args.output,
        model=args.model,
        agent_exit_code=args.agent_exit_code,
    )
    print(f"{'PASS' if accepted else 'FAIL'} {args.case_root.name}: {args.output}")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
