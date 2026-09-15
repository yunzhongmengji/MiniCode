"""Command-line interface for MiniCode."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from minicode.core.checkpoints import RunCheckpoint
from minicode.core.events import EventLedger, InMemoryEventLedger
from minicode.core.file_checkpoint_store import FileCheckpointStore
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


class _CliCheckpointError(ValueError):
    """A checkpoint problem that can be explained to CLI users."""


async def _execute_coding_task(
    starting_input: str | RunCheckpoint,
    *,
    max_turns: int,
    max_tool_calls: int,
    event_ledger: EventLedger,
    artifact_store: ArtifactStore | None = None,
    max_inline_tool_result_bytes: int | None = None,
) -> RunResult:
    """Compose and execute one fresh or resumed coding task."""
    try:
        config = DashScopeConfig.from_environment(os.environ)
    except ValueError as error:
        raise _CliConfigurationError(str(error)) from error

    client = build_dashscope_client(config)

    try:
        workspace_root = Path.cwd().resolve()
        checkpoint_store = FileCheckpointStore(
            _checkpoint_root(
                workspace_root,
                os.environ,
            )
        )
        model = build_dashscope_model(
            config,
            client=client,
        )
        agent = build_coding_agent(
            model=model,
            workspace=Workspace(
                root=workspace_root,
            ),
            process_runner=AsyncioProcessRunner(),
            approver=ConsoleToolApprover(),
            event_ledger=event_ledger,
            artifact_store=artifact_store,
            checkpoint_store=checkpoint_store,
            max_turns=max_turns,
            max_tool_calls=max_tool_calls,
            max_inline_tool_result_bytes=max_inline_tool_result_bytes,
        )

        if isinstance(starting_input, RunCheckpoint):
            return await agent.resume(starting_input)

        return await agent.run(starting_input)
    finally:
        await client.close()


def _checkpoint_root(
    workspace_root: Path,
    environment: Mapping[str, str],
) -> Path:
    """Return the state directory for one workspace's checkpoints."""
    configured_state_home = environment.get("XDG_STATE_HOME")

    if configured_state_home:
        state_home = Path(configured_state_home).expanduser()

        if not state_home.is_absolute():
            raise _CliConfigurationError("XDG_STATE_HOME must be an absolute path")
    else:
        state_home = Path.home() / ".local" / "state"

    workspace_key = hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()
    return state_home / "minicode" / "checkpoints" / workspace_key


def _load_checkpoint(
    run_id: str,
    *,
    workspace_root: Path,
    environment: Mapping[str, str],
) -> RunCheckpoint:
    """Load one run's latest checkpoint from this workspace."""
    try:
        store = FileCheckpointStore(
            _checkpoint_root(
                workspace_root,
                environment,
            )
        )
        checkpoint = store.latest(run_id)
    except _CliConfigurationError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise _CliCheckpointError(
            f"could not load checkpoint for {run_id}: {error}"
        ) from error

    if checkpoint is None:
        raise _CliCheckpointError(f"no checkpoint found for {run_id}")

    if checkpoint.is_completed:
        raise _CliCheckpointError(f"run {run_id} is already completed; cannot resume")

    return checkpoint


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


def _positive_integer(value: str) -> int:
    """Parse one positive CLI integer."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error

    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")

    return parsed


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
    run_parser.add_argument(
        "--max-turns",
        type=_positive_integer,
        default=8,
        help="Maximum model turns (default: 8).",
    )
    run_parser.add_argument(
        "--max-tool-calls",
        type=_positive_integer,
        default=8,
        help="Maximum model-requested tool calls (default: 8).",
    )

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a coding task from its latest checkpoint.",
    )
    resume_parser.add_argument(
        "run_id",
        help="The Run ID printed by the original command.",
    )
    resume_parser.add_argument(
        "--trace",
        action="store_true",
        help="Print the ordered execution trace.",
    )
    resume_parser.add_argument(
        "--max-turns",
        type=_positive_integer,
        default=8,
        help="Maximum total model turns (default: 8).",
    )
    resume_parser.add_argument(
        "--max-tool-calls",
        type=_positive_integer,
        default=8,
        help="Maximum total model-requested tool calls (default: 8).",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    max_inline_tool_result_bytes: int | None = None,
) -> int:
    """Run the MiniCode command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if args.dry_run:
            print(f"Task: {args.task}")
            print("Dry run: no files were changed.")
            return 0

        run_id = f"run_{uuid4().hex}"
        starting_input: str | RunCheckpoint = args.task
        print(
            f"Run ID: {run_id}",
            file=sys.stderr,
        )
    else:
        run_id = args.run_id

        try:
            starting_input = _load_checkpoint(
                run_id,
                workspace_root=Path.cwd().resolve(),
                environment=os.environ,
            )
        except _CliConfigurationError as error:
            print(
                f"Configuration error: {error}",
                file=sys.stderr,
            )
            return 2
        except _CliCheckpointError as error:
            print(
                f"Checkpoint error: {error}",
                file=sys.stderr,
            )
            return 2

        print(
            f"Resuming Run ID: {run_id}",
            file=sys.stderr,
        )

    event_ledger = InMemoryEventLedger(
        run_id=run_id,
    )
    artifact_store = InMemoryArtifactStore() if args.trace else None

    try:
        try:
            result = asyncio.run(
                _execute_coding_task(
                    starting_input,
                    max_turns=args.max_turns,
                    max_tool_calls=args.max_tool_calls,
                    event_ledger=event_ledger,
                    artifact_store=artifact_store,
                    max_inline_tool_result_bytes=max_inline_tool_result_bytes,
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


if __name__ == "__main__":
    raise SystemExit(main())
