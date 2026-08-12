"""Command-line interface for MiniCode."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="minicode",
        description="A local-first, auditable coding agent runtime.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a coding task.",
    )
    run_parser.add_argument(
        "task",
        help="The coding task to execute.",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the task without executing it.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the MiniCode command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if args.dry_run:
            print(f"Task: {args.task}")
            print("Dry run: no files were changed.")
            return 0

        print("Task execution is not implemented yet.", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
