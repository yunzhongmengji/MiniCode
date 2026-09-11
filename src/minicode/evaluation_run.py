"""Start one Coding Agent evaluation from its case contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from minicode import cli
from minicode.evaluation_case import load_case_manifest


def build_coding_run_arguments(
    case_root: Path,
) -> tuple[str, ...]:
    """Build CLI arguments from one validated evaluation case."""
    resolved_case_root = case_root.resolve(strict=True)
    manifest = load_case_manifest(resolved_case_root)
    task = (resolved_case_root / "task.txt").read_text(
        encoding="utf-8",
    )

    if not task.strip():
        raise ValueError("evaluation task must not be blank")

    return (
        "run",
        task.strip(),
        "--max-turns",
        str(manifest.budget.max_turns),
        "--max-tool-calls",
        str(manifest.budget.max_tool_calls),
        "--trace",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the evaluation-run argument parser."""
    parser = argparse.ArgumentParser(
        description="Run a prepared MiniCode evaluation workspace.",
    )
    parser.add_argument(
        "--case-root",
        type=Path,
        required=True,
        help="Evaluation case containing case.json and task.txt.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the case task in the current working directory."""
    args = build_parser().parse_args(argv)
    return cli.main(
        build_coding_run_arguments(args.case_root),
    )


if __name__ == "__main__":
    raise SystemExit(main())
