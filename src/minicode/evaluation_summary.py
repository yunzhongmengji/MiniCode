"""Summarize recorded Coding Agent evaluation results."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True, slots=True)
class _RecordedEvaluation:
    case_id: str
    accepted: bool
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


def summarize_results(results_root: Path) -> str:
    """Render a Markdown summary of every result below one directory."""
    result_paths = tuple(sorted(results_root.rglob("result.json")))

    if not result_paths:
        raise ValueError(f"no result.json files found below {results_root}")

    results = tuple(_load_result(path) for path in result_paths)
    rows = [
        "| Case | Accepted | Model calls | Tool executions | Input tokens | Output tokens | Changes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for result in results:
        rows.append(
            "| "
            f"{result.case_id} | "
            f"{'yes' if result.accepted else 'no'} | "
            f"{result.model_call_count} | "
            f"{result.tool_execution_count} | "
            f"{result.input_tokens} | "
            f"{result.output_tokens} | "
            f"{result.workspace_change_count} |"
        )

    accepted_count = sum(result.accepted for result in results)
    operational_failure_count = sum(
        result.agent_exit_code != 0 or result.run_outcome != "succeeded"
        for result in results
    )
    rate = accepted_count / len(results) * 100
    models = ", ".join(sorted({result.model for result in results}))
    commits = ", ".join(sorted({result.minicode_commit[:7] for result in results}))

    rows.extend(
        (
            "",
            f"- Runs: {len(results)}",
            f"- Accepted: {accepted_count}/{len(results)} ({rate:.1f}%)",
            f"- Operational failures: {operational_failure_count}",
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


def _load_result(path: Path) -> _RecordedEvaluation:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(decoded, Mapping):
        raise TypeError(f"evaluation result must be an object: {path}")

    result = cast(Mapping[str, object], decoded)
    schema_version = _required_integer(result, "schema_version", path)

    if schema_version != 1:
        raise ValueError(
            f"unsupported evaluation result schema {schema_version}: {path}"
        )

    run = _required_mapping(result, "run", path)
    workspace_status = result.get("workspace_status")

    if not isinstance(workspace_status, list):
        raise TypeError(f"workspace_status must be a list: {path}")

    return _RecordedEvaluation(
        case_id=_required_string(result, "case_id", path),
        accepted=_required_boolean(result, "accepted", path),
        agent_exit_code=_required_integer(result, "agent_exit_code", path),
        model=_required_string(result, "model", path),
        minicode_commit=_required_string(result, "minicode_commit", path),
        minicode_dirty=_required_boolean(result, "minicode_dirty", path),
        run_outcome=_required_string(run, "outcome", path),
        model_call_count=_required_integer(run, "model_call_count", path),
        tool_execution_count=_required_integer(
            run,
            "tool_execution_count",
            path,
        ),
        input_tokens=_required_integer(run, "input_tokens", path),
        output_tokens=_required_integer(run, "output_tokens", path),
        workspace_change_count=len(workspace_status),
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print one summary for a recorded evaluation batch."""
    args = build_parser().parse_args(argv)
    print(summarize_results(args.results_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
