"""Thin CLI entry point reusing MiniCode's unified SQLite RecoverableAgentRuntime."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Sequence
from pathlib import Path

import uvicorn

from minicode.models import (
    DashScopeConfig,
    Model,
    build_dashscope_client,
    build_dashscope_model,
)
from minicode.runtime import (
    SessionRunResult,
    Workspace,
    build_local_tool_registry,
    build_runtime,
    replay,
)
from minicode.schemas import ApprovalDecision
from minicode.skills.lazy import LazySkillRegistry
from minicode.storage import SqliteRuntimeStorage


def _default_db_path(workspace: Path) -> Path:
    return workspace / ".minicode" / "runtime.sqlite3"


def _build_default_model() -> Model:
    config = DashScopeConfig.from_environment(os.environ)
    client = build_dashscope_client(config)
    return build_dashscope_model(config, client=client)


def _print_result(result: SessionRunResult) -> None:
    print(f"session_id: {result.session_id}")
    print(f"status: {result.status.value} (step={result.step})")
    if result.pending_approval is not None:
        p = result.pending_approval
        print(
            f"approval_required: tool={p.tool_name} risk={p.risk_level.value} "
            f"call_id={p.call_id}"
        )
        print(
            f"Run `minicode approve {result.session_id} --decision approve` to continue."
        )
    if result.final_answer:
        print(result.final_answer)


def build_parser() -> argparse.ArgumentParser:
    """Create the unified MiniCode CLI parser."""
    parser = argparse.ArgumentParser(
        prog="minicode", description="MiniCode Agent Runtime"
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--skills-dir", type=Path, default=None)
    parser.add_argument("--max-context-tokens", type=int, default=4096)

    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Start a new durable coding session.")
    run_p.add_argument("task", help="Task description.")
    run_p.add_argument("--session-id", default=None)
    run_p.add_argument("--max-turns", type=int, default=8)
    run_p.add_argument("--max-tool-calls", type=int, default=16)

    resume_p = sub.add_parser("resume", help="Resume an interrupted session.")
    resume_p.add_argument("session_id")

    approve_p = sub.add_parser("approve", help="Approve or reject a paused tool call.")
    approve_p.add_argument("session_id")
    approve_p.add_argument(
        "--decision",
        choices=("approve", "reject"),
        default="approve",
    )
    approve_p.add_argument("--reason", default="")

    replay_p = sub.add_parser(
        "replay", help="Print chronological read-only audit replay."
    )
    replay_p.add_argument("session_id")

    serve_p = sub.add_parser("serve", help="Start the FastAPI + SSE server.")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)

    return parser


async def _dispatch_async(
    args: argparse.Namespace,
    *,
    model_factory: Callable[[], Model] | None = None,
) -> int:
    workspace_root = args.workspace.resolve()
    db_path = _default_db_path(workspace_root) if args.db is None else args.db
    storage = SqliteRuntimeStorage(db_path)

    try:
        if args.command == "replay":
            print(replay(args.session_id, storage).render_text())
            return 0

        skill_registry = (
            LazySkillRegistry.discover(args.skills_dir)
            if args.skills_dir is not None
            else None
        )
        extra_instructions = (
            (skill_registry.render_metadata_prompt(),)
            if skill_registry is not None
            else ()
        )
        tool_registry = build_local_tool_registry(
            workspace=Workspace(workspace_root),
            skill_registry=skill_registry,
        )
        model = _build_default_model() if model_factory is None else model_factory()
        runtime = build_runtime(
            model=model,
            storage=storage,
            tool_registry=tool_registry,
            max_context_tokens=args.max_context_tokens,
            extra_instructions=extra_instructions,
            max_turns=getattr(args, "max_turns", 8),
            max_tool_calls=getattr(args, "max_tool_calls", 16),
        )

        if args.command == "run":
            result = await runtime.start(args.task, session_id=args.session_id)
        elif args.command == "resume":
            result = await runtime.resume(args.session_id)
        else:
            decision = ApprovalDecision(args.decision)
            result = await runtime.resolve_approval(
                args.session_id,
                decision,
                reason=args.reason,
                continue_run=decision is ApprovalDecision.APPROVE,
            )

        _print_result(result)
        return 0
    finally:
        storage.close()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        os.environ.setdefault("MINICODE_WORKSPACE", str(args.workspace.resolve()))
        if args.db is not None:
            os.environ["MINICODE_DB_PATH"] = str(args.db.resolve())
        uvicorn.run(
            "minicode.api.app:create_default_app",
            factory=True,
            host=args.host,
            port=args.port,
        )
        return 0
    return asyncio.run(_dispatch_async(args))
