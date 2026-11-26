"""Tests for cross-process crash recovery, high-risk approval, and replay."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from minicode.models import ModelResponse, ScriptedModel
from minicode.runtime import (
    ApprovalPendingError,
    InvalidSessionStateError,
    RecoverableAgentRuntime,
    ToolRiskPolicy,
    replay,
)
from minicode.schemas import (
    ApprovalDecision,
    EventType,
    RiskLevel,
    SessionStatus,
    TokenUsage,
    ToolCallRecord,
)
from minicode.storage import SqliteRuntimeStorage
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class _PathArgs(ToolArguments):
    path: str


class _ShellArgs(ToolArguments):
    command: str


class _FunctionTool:
    """Minimal executable tool adapter for runtime tests."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        arguments_type: type[ToolArguments],
        handler: Callable[[ToolArguments], Awaitable[str]],
    ) -> None:
        self._spec = ToolSpec(
            name=name,
            description=description,
            arguments_type=arguments_type,
        )
        self._handler = handler

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        return await self._handler(arguments)


class _CrashOnceError(RuntimeError):
    """Simulated sudden process crash during execution."""


@pytest.mark.asyncio
async def test_crash_mid_tool_batch_and_cross_process_resume(tmp_path: Path) -> None:
    """Simulate a crash between tool calls, restart storage/runtime, and resume."""
    db_path = tmp_path / "crash_recovery.sqlite3"
    executed_calls: list[tuple[str, str]] = []
    should_crash_second_read = {"crash": True}

    async def handle_read(args: ToolArguments) -> str:
        assert isinstance(args, _PathArgs)
        if args.path == "b.py" and should_crash_second_read["crash"]:
            should_crash_second_read["crash"] = False
            raise _CrashOnceError("simulated SIGKILL before completing b.py")
        executed_calls.append(("read_file", args.path))
        return f"contents of {args.path}"

    def build_registry() -> ToolRegistry:
        reg = ToolRegistry()
        reg.register(
            _FunctionTool(
                name="read_file",
                description="Read a workspace file.",
                arguments_type=_PathArgs,
                handler=handle_read,
            )
        )
        return reg

    # Process 1: reasoning proposes two read_file calls; first succeeds and checkpoints,
    # second crashes abruptly before its checkpoint can be written.
    storage_proc1 = SqliteRuntimeStorage(db_path)
    model_proc1 = ScriptedModel(
        (
            ModelResponse(
                content="I will inspect a.py and b.py first.",
                tool_calls=(
                    ToolCallRecord(
                        call_id="c1", name="read_file", arguments={"path": "a.py"}
                    ),
                    ToolCallRecord(
                        call_id="c2", name="read_file", arguments={"path": "b.py"}
                    ),
                ),
                usage=TokenUsage(input_tokens=100, output_tokens=30),
            ),
        )
    )
    runtime_proc1 = RecoverableAgentRuntime(
        model=model_proc1,
        tool_registry=build_registry(),
        storage=storage_proc1,
    )

    with pytest.raises(_CrashOnceError):
        await runtime_proc1.start("Inspect a.py and b.py", session_id="sess_crash_1")

    # Verify first tool call was durably committed before the crash.
    pre_restart_cp = storage_proc1.checkpoint_store.load_latest("sess_crash_1")
    assert pre_restart_cp is not None
    assert pre_restart_cp.status is SessionStatus.RUNNING
    assert pre_restart_cp.tool_calls_used == 1
    assert [call.call_id for call in pre_restart_cp.pending_tool_calls] == ["c2"]
    storage_proc1.close()

    # Process 2: brand-new SQLite storage + brand-new runtime resumes from disk.
    storage_proc2 = SqliteRuntimeStorage(db_path)
    try:
        model_proc2 = ScriptedModel(
            (
                ModelResponse(
                    content="Both a.py and b.py were inspected successfully.",
                    usage=TokenUsage(input_tokens=140, output_tokens=25),
                ),
            )
        )
        runtime_proc2 = RecoverableAgentRuntime(
            model=model_proc2,
            tool_registry=build_registry(),
            storage=storage_proc2,
        )

        result = await runtime_proc2.resume("sess_crash_1")
        assert result.status is SessionStatus.COMPLETED
        assert result.final_answer == "Both a.py and b.py were inspected successfully."
        assert result.turns_used == 2
        assert result.tool_calls_used == 2
        assert result.total_input_tokens == 240
        assert result.total_output_tokens == 55

        # Crucial invariant: a.py must NOT be re-executed after resume!
        assert executed_calls == [("read_file", "a.py"), ("read_file", "b.py")]

        # Replay verifies complete chronological audit trail across the restart.
        trajectory = replay("sess_crash_1", storage_proc2)
        assert trajectory.status is SessionStatus.COMPLETED
        assert trajectory.total_input_tokens == 240
        assert trajectory.total_output_tokens == 55
        event_types = [entry.event_type for entry in trajectory.entries]
        assert EventType.SESSION_STARTED in event_types
        assert EventType.SESSION_RESUMED in event_types
        assert EventType.SESSION_COMPLETED in event_types
        rendered = trajectory.render_text()
        assert "I will inspect a.py and b.py first." in rendered
        assert "contents of b.py" in rendered
    finally:
        storage_proc2.close()


@pytest.mark.asyncio
async def test_high_risk_tool_pauses_for_approval_and_continues_on_approve(
    tmp_path: Path,
) -> None:
    """High-risk shell tool pauses in WAITING_APPROVAL and resumes after approve."""
    db_path = tmp_path / "approval_approve.sqlite3"
    shell_invocations: list[str] = []

    async def handle_shell(args: ToolArguments) -> str:
        assert isinstance(args, _ShellArgs)
        shell_invocations.append(args.command)
        return f"ran: {args.command}"

    registry = ToolRegistry()
    registry.register(
        _FunctionTool(
            name="run_shell",
            description="Run a shell command.",
            arguments_type=_ShellArgs,
            handler=handle_shell,
        )
    )
    risk_policy = ToolRiskPolicy(
        tool_risks={"run_shell": RiskLevel.EXECUTE_SHELL},
        approval_required_levels=(RiskLevel.WRITE_FILE, RiskLevel.EXECUTE_SHELL),
    )

    storage = SqliteRuntimeStorage(db_path)
    try:
        model = ScriptedModel(
            (
                ModelResponse(
                    content="Need to run pytest via shell.",
                    tool_calls=(
                        ToolCallRecord(
                            call_id="shell_1",
                            name="run_shell",
                            arguments={"command": "pytest -q"},
                        ),
                    ),
                    usage=TokenUsage(input_tokens=80, output_tokens=20),
                ),
                ModelResponse(
                    content="All tests passed.",
                    usage=TokenUsage(input_tokens=110, output_tokens=15),
                ),
            )
        )
        runtime = RecoverableAgentRuntime(
            model=model,
            tool_registry=registry,
            storage=storage,
            risk_policy=risk_policy,
        )

        paused = await runtime.start("Run test suite", session_id="sess_approve_1")
        assert paused.status is SessionStatus.WAITING_APPROVAL
        assert paused.pending_approval is not None
        assert paused.pending_approval.call_id == "shell_1"
        assert paused.pending_approval.tool_name == "run_shell"
        assert paused.pending_approval.risk_level is RiskLevel.EXECUTE_SHELL
        assert shell_invocations == []

        # Plain resume without explicit approval must be rejected.
        with pytest.raises(ApprovalPendingError):
            await runtime.resume("sess_approve_1")

        # External caller approves -> tool executes and session finishes.
        completed = await runtime.approve(
            "sess_approve_1",
            reason="reviewer verified pytest command",
        )
        assert completed.status is SessionStatus.COMPLETED
        assert completed.final_answer == "All tests passed."
        assert completed.tool_calls_used == 1
        assert shell_invocations == ["pytest -q"]

        # Replay must include thinking, approval request, approval decision, and output.
        trajectory = replay("sess_approve_1", storage)
        assert trajectory.status is SessionStatus.COMPLETED
        approval_entries = [
            entry
            for entry in trajectory.entries
            if entry.event_type is EventType.APPROVAL_DECIDED
        ]
        assert len(approval_entries) == 1
        assert approval_entries[0].approval_decision is ApprovalDecision.APPROVE
        assert approval_entries[0].risk_level is RiskLevel.EXECUTE_SHELL
        rendered = trajectory.render_text()
        assert "approval: approve" in rendered
        assert "ran: pytest -q" in rendered
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_high_risk_tool_reject_aborts_session_without_execution(
    tmp_path: Path,
) -> None:
    """Rejecting a pending high-risk tool aborts the session and never runs it."""
    db_path = tmp_path / "approval_reject.sqlite3"
    delete_called = False

    async def handle_delete(args: ToolArguments) -> str:
        nonlocal delete_called
        delete_called = True
        return f"deleted {args}"

    registry = ToolRegistry()
    registry.register(
        _FunctionTool(
            name="delete_file",
            description="Delete a file.",
            arguments_type=_PathArgs,
            handler=handle_delete,
        )
    )
    storage = SqliteRuntimeStorage(db_path)
    try:
        model = ScriptedModel(
            (
                ModelResponse(
                    content="I will delete production.db.",
                    tool_calls=(
                        ToolCallRecord(
                            call_id="del_1",
                            name="delete_file",
                            arguments={"path": "production.db"},
                        ),
                    ),
                ),
            )
        )
        runtime = RecoverableAgentRuntime(
            model=model,
            tool_registry=registry,
            storage=storage,
        )

        paused = await runtime.start("Clean up workspace", session_id="sess_reject_1")
        assert paused.status is SessionStatus.WAITING_APPROVAL
        assert paused.pending_approval is not None
        assert paused.pending_approval.tool_name == "delete_file"

        aborted = await runtime.reject(
            "sess_reject_1",
            reason="dangerous deletion blocked",
        )
        assert aborted.status is SessionStatus.ABORTED
        assert aborted.pending_approval is None
        assert delete_called is False

        # Terminal aborted session cannot be resumed.
        with pytest.raises(InvalidSessionStateError):
            await runtime.resume("sess_reject_1")

        # Read-only replay does not mutate ledger state and records the rejection.
        events_before = storage.event_ledger.list_events("sess_reject_1")
        trajectory = replay("sess_reject_1", storage)
        events_after = storage.event_ledger.list_events("sess_reject_1")
        assert events_before == events_after
        assert trajectory.status is SessionStatus.ABORTED
        assert any(
            entry.event_type is EventType.APPROVAL_DECIDED
            and entry.approval_decision is ApprovalDecision.REJECT
            for entry in trajectory.entries
        )
    finally:
        storage.close()
