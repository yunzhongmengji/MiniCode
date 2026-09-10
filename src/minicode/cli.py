"""Command-line interface for MiniCode."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from minicode.coding_agent import build_coding_agent
from minicode.console_approval import ConsoleToolApprover
from minicode.core.artifacts import (
    ArtifactStore,
    InMemoryArtifactStore,
)
from minicode.core.events import EventLedger, InMemoryEventLedger
from minicode.core.model import ModelError
from minicode.core.query_loop import RunResult, StopReason
from minicode.core.tool_calls import JsonValue
from minicode.models.dashscope import (
    DashScopeConfig,
    build_dashscope_client,
    build_dashscope_model,
)
from minicode.tools.process import AsyncioProcessRunner
from minicode.workspace import Workspace


class _CliConfigurationError(ValueError):
    """A configuration problem that can be explained to CLI users."""


async def _run_coding_task(
    task: str,
    *,
    event_ledger: EventLedger | None = None,
    artifact_store: ArtifactStore | None = None,
) -> RunResult:
    """Compose and run one real DashScope-backed coding task."""
    try:
        config = DashScopeConfig.from_environment(os.environ)
    except ValueError as error:
        raise _CliConfigurationError(str(error)) from error

    client = build_dashscope_client(config)

    try:
        model = build_dashscope_model(
            config,
            client=client,
        )
        agent = build_coding_agent(
            model=model,
            workspace=Workspace(
                root=Path.cwd(),
            ),
            process_runner=AsyncioProcessRunner(),
            approver=ConsoleToolApprover(),
            event_ledger=event_ledger,
            artifact_store=artifact_store,
        )

        return await agent.run(task)
    finally:
        await client.close()


def _to_json_output(
    value: JsonValue,
) -> object:
    """Convert frozen event data into JSON-serializable containers."""
    if isinstance(value, Mapping):
        return {key: _to_json_output(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_json_output(item) for item in value]

    return value


def _print_trace(
    event_ledger: InMemoryEventLedger,
) -> None:
    """Render one completed run's ordered events to stderr."""
    print(
        f"Trace {event_ledger.run_id}",
        file=sys.stderr,
    )

    for event in event_ledger.events:
        payload = json.dumps(
            _to_json_output(event.payload),
            ensure_ascii=False,
            sort_keys=True,
        )
        print(
            f"{event.sequence:03d} {event.kind.value} {payload}",
            file=sys.stderr,
        )


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
    run_parser.add_argument(
        "--trace",
        action="store_true",
        help="Print the ordered execution trace.",
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

        event_ledger = InMemoryEventLedger(
            run_id=f"run_{uuid4().hex}",
        )
        artifact_store = InMemoryArtifactStore() if args.trace else None

        try:
            try:
                result = asyncio.run(
                    _run_coding_task(
                        args.task,
                        event_ledger=event_ledger,
                        artifact_store=artifact_store,
                    )
                )
            except _CliConfigurationError as error:
                print(
                    f"Configuration error: {error}",
                    file=sys.stderr,
                )
                return 2
            except ModelError as error:
                print(
                    f"Model error: {error}",
                    file=sys.stderr,
                )
                return 1
            except TimeoutError:
                print(
                    "Task timed out.",
                    file=sys.stderr,
                )
                return 1
            except KeyboardInterrupt:
                print(
                    "Task cancelled by user.",
                    file=sys.stderr,
                )
                return 130

            if result.response.content:
                print(result.response.content)

            if result.stop_reason is not StopReason.COMPLETED:
                print(
                    f"Task stopped before completion: {result.stop_reason.value}",
                    file=sys.stderr,
                )
                return 1

            return 0
        finally:
            if args.trace:
                _print_trace(event_ledger)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
