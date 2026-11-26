"""Async task execution service decoupling Agent runs from SSE streaming."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from uuid import uuid4

from minicode.api.broker import TaskEventBroker
from minicode.models.base import Model
from minicode.runtime.engine import (
    ApprovalPendingError,
    InvalidSessionStateError,
    RecoverableAgentRuntime,
    SessionNotFoundError,
)
from minicode.runtime.factory import build_runtime
from minicode.runtime.policy import ToolRiskPolicy, build_default_risk_policy
from minicode.runtime.replay import SessionReplay, replay
from minicode.runtime.workspace import Workspace
from minicode.sandbox.base import SandboxConfig
from minicode.sandbox.docker import DockerSandbox
from minicode.sandbox.tools import build_sandbox_tool_registry
from minicode.schemas.api import (
    ApproveTaskRequest,
    CreateTaskRequest,
    SSEEventPayload,
    TaskResponse,
)
from minicode.schemas.checkpoints import (
    ApprovalDecision,
    SessionCheckpoint,
    SessionStatus,
)
from minicode.schemas.events import EventType, LedgerEvent, LedgerEventInput
from minicode.storage.store import SqliteRuntimeStorage
from minicode.tools.registry import ToolRegistry

_STREAM_STOP_EVENTS: frozenset[EventType] = frozenset(
    {
        EventType.SESSION_PAUSED,
        EventType.SESSION_COMPLETED,
        EventType.SESSION_ABORTED,
        EventType.SESSION_FAILED,
    }
)

ModelFactory = Callable[[], Model]
SandboxFactory = Callable[[str, Path], DockerSandbox]
ToolRegistryFactory = Callable[[DockerSandbox, Workspace], ToolRegistry]


class AgentTaskService:
    """Manage background sandboxed agent sessions and live SSE event streaming."""

    def __init__(
        self,
        *,
        storage: SqliteRuntimeStorage,
        workspace_root: Path,
        model_factory: ModelFactory,
        sandbox_config: SandboxConfig | None = None,
        sandbox_factory: SandboxFactory | None = None,
        tool_registry_factory: ToolRegistryFactory | None = None,
        risk_policy: ToolRiskPolicy | None = None,
        default_max_context_tokens: int | None = None,
    ) -> None:
        self._storage = storage
        self._workspace_root = workspace_root.resolve()
        self._model_factory = model_factory
        self._sandbox_config = (
            SandboxConfig() if sandbox_config is None else sandbox_config
        )
        self._sandbox_factory = sandbox_factory
        self._tool_registry_factory = tool_registry_factory
        self._risk_policy = (
            build_default_risk_policy() if risk_policy is None else risk_policy
        )
        self._default_max_context_tokens = default_max_context_tokens
        self._broker = TaskEventBroker()
        self._storage.add_event_listener(self._broker.publish)
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._task_configs: dict[str, tuple[int, int, int | None]] = {}

    @property
    def storage(self) -> SqliteRuntimeStorage:
        """Return the underlying SQLite runtime storage."""
        return self._storage

    def _create_sandbox(self, session_id: str) -> DockerSandbox:
        if self._sandbox_factory is not None:
            return self._sandbox_factory(session_id, self._workspace_root)
        return DockerSandbox(
            session_id=session_id,
            workspace_root=self._workspace_root,
            config=self._sandbox_config,
        )

    def _build_runtime(
        self,
        *,
        sandbox: DockerSandbox,
        max_turns: int,
        max_tool_calls: int,
        max_context_tokens: int | None,
    ) -> RecoverableAgentRuntime:
        workspace = Workspace(self._workspace_root)
        registry = (
            self._tool_registry_factory(sandbox, workspace)
            if self._tool_registry_factory is not None
            else build_sandbox_tool_registry(sandbox=sandbox, workspace=workspace)
        )
        effective_budget = (
            max_context_tokens
            if max_context_tokens is not None
            else self._default_max_context_tokens
        )
        return build_runtime(
            model=self._model_factory(),
            storage=self._storage,
            tool_registry=registry,
            risk_policy=self._risk_policy,
            max_context_tokens=effective_budget,
            max_turns=max_turns,
            max_tool_calls=max_tool_calls,
        )

    @staticmethod
    def _to_response(checkpoint: SessionCheckpoint) -> TaskResponse:
        return TaskResponse(
            task_id=checkpoint.session_id,
            status=checkpoint.status,
            step=checkpoint.step,
            turns_used=checkpoint.turns_used,
            tool_calls_used=checkpoint.tool_calls_used,
            total_input_tokens=checkpoint.total_input_tokens,
            total_output_tokens=checkpoint.total_output_tokens,
            final_answer=checkpoint.final_answer,
            pending_approval=checkpoint.pending_approval,
            stream_url=f"/tasks/{checkpoint.session_id}/stream",
        )

    async def create_task(self, request: CreateTaskRequest) -> TaskResponse:
        """Create a new coding task and schedule sandboxed execution in background."""
        session_id = (
            f"task_{uuid4().hex[:16]}"
            if request.session_id is None
            else request.session_id
        )
        if self._storage.checkpoint_store.load_latest(session_id) is not None:
            raise InvalidSessionStateError(f"task '{session_id}' already exists")

        self._task_configs[session_id] = (
            request.max_turns,
            request.max_tool_calls,
            request.max_context_tokens,
        )
        self._schedule_background(
            session_id,
            self._run_new_task(
                session_id=session_id,
                task=request.task,
                max_turns=request.max_turns,
                max_tool_calls=request.max_tool_calls,
                max_context_tokens=request.max_context_tokens,
            ),
        )
        return TaskResponse(
            task_id=session_id,
            status=SessionStatus.RUNNING,
            step=0,
            stream_url=f"/tasks/{session_id}/stream",
        )

    async def approve_task(
        self,
        task_id: str,
        request: ApproveTaskRequest,
    ) -> TaskResponse:
        """Submit an approve/reject decision for a WAITING_APPROVAL task."""
        checkpoint = self._storage.checkpoint_store.load_latest(task_id)
        if checkpoint is None:
            raise SessionNotFoundError(f"task '{task_id}' not found")
        if checkpoint.status is not SessionStatus.WAITING_APPROVAL:
            raise InvalidSessionStateError(
                f"task '{task_id}' is not waiting for approval "
                f"(status='{checkpoint.status.value}')"
            )

        max_turns, max_tool_calls, max_ctx = self._task_configs.get(
            task_id, (8, 16, self._default_max_context_tokens)
        )

        if request.decision is ApprovalDecision.REJECT:
            runtime = build_runtime(
                model=self._model_factory(),
                storage=self._storage,
                tool_registry=ToolRegistry(),
                risk_policy=self._risk_policy,
            )
            await runtime.reject(task_id, reason=request.reason)
            updated = self._storage.checkpoint_store.load_latest(task_id)
            assert updated is not None
            return self._to_response(updated)

        self._schedule_background(
            task_id,
            self._run_approved_task(
                session_id=task_id,
                reason=request.reason,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_context_tokens=max_ctx,
            ),
        )
        return TaskResponse(
            task_id=task_id,
            status=SessionStatus.RUNNING,
            step=checkpoint.step,
            turns_used=checkpoint.turns_used,
            tool_calls_used=checkpoint.tool_calls_used,
            total_input_tokens=checkpoint.total_input_tokens,
            total_output_tokens=checkpoint.total_output_tokens,
            stream_url=f"/tasks/{task_id}/stream",
        )

    async def resume_task(self, task_id: str) -> TaskResponse:
        """Resume an interrupted task from its latest SQLite checkpoint."""
        checkpoint = self._storage.checkpoint_store.load_latest(task_id)
        if checkpoint is None:
            raise SessionNotFoundError(f"task '{task_id}' not found")
        if checkpoint.status is SessionStatus.WAITING_APPROVAL:
            raise ApprovalPendingError(
                f"task '{task_id}' is waiting approval; call POST /tasks/{task_id}/approve"
            )
        if checkpoint.status in (SessionStatus.COMPLETED, SessionStatus.ABORTED):
            raise InvalidSessionStateError(
                f"task '{task_id}' is already in terminal status '{checkpoint.status.value}'"
            )

        max_turns, max_tool_calls, max_ctx = self._task_configs.get(
            task_id, (8, 16, self._default_max_context_tokens)
        )
        self._schedule_background(
            task_id,
            self._run_resumed_task(
                session_id=task_id,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_context_tokens=max_ctx,
            ),
        )
        return TaskResponse(
            task_id=task_id,
            status=SessionStatus.RUNNING,
            step=checkpoint.step,
            turns_used=checkpoint.turns_used,
            tool_calls_used=checkpoint.tool_calls_used,
            total_input_tokens=checkpoint.total_input_tokens,
            total_output_tokens=checkpoint.total_output_tokens,
            stream_url=f"/tasks/{task_id}/stream",
        )

    def get_replay(self, task_id: str) -> SessionReplay:
        """Return read-only chronological trajectory replay for a task."""
        return replay(task_id, self._storage)

    def get_task(self, task_id: str) -> TaskResponse:
        """Return latest durable status for a task."""
        checkpoint = self._storage.checkpoint_store.load_latest(task_id)
        if checkpoint is None:
            raise SessionNotFoundError(f"task '{task_id}' not found")
        return self._to_response(checkpoint)

    async def stream_events(self, task_id: str) -> AsyncIterator[str]:
        """Yield SSE frames for historical and live events without blocking."""
        queue = self._broker.subscribe(task_id)
        try:
            last_seq = 0
            historical = self._storage.event_ledger.list_events(task_id)
            for event in historical:
                last_seq = event.sequence
                yield self._format_sse(event)

            latest_cp = self._storage.checkpoint_store.load_latest(task_id)
            if (
                latest_cp is not None
                and latest_cp.status is not SessionStatus.RUNNING
                and task_id not in self._active_tasks
            ):
                return

            if (
                not historical
                and latest_cp is None
                and task_id not in self._active_tasks
            ):
                raise SessionNotFoundError(f"task '{task_id}' not found")

            while True:
                event = await queue.get()
                if event.sequence <= last_seq:
                    continue
                last_seq = event.sequence
                yield self._format_sse(event)
                if event.event_type in _STREAM_STOP_EVENTS:
                    return
        finally:
            self._broker.unsubscribe(task_id, queue)

    async def shutdown(self) -> None:
        """Cancel active background tasks and release resources."""
        tasks = list(self._active_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._storage.remove_event_listener(self._broker.publish)

    def _schedule_background(
        self,
        session_id: str,
        coro: asyncio.Future[None] | asyncio.Task[None] | object,
    ) -> None:
        existing = self._active_tasks.get(session_id)
        if existing is not None and not existing.done():
            raise InvalidSessionStateError(f"task '{session_id}' is already running")

        async def _runner() -> None:
            try:
                await coro  # type: ignore[misc]
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                self._record_failure(session_id, error)
            finally:
                self._active_tasks.pop(session_id, None)

        self._active_tasks[session_id] = asyncio.create_task(_runner())

    def _record_failure(self, session_id: str, error: Exception) -> None:
        latest = self._storage.checkpoint_store.load_latest(session_id)
        if latest is None:
            latest = SessionCheckpoint(
                session_id=session_id,
                step=0,
                status=SessionStatus.FAILED,
            )
        else:
            latest = latest.model_copy(
                update={
                    "step": latest.step + 1,
                    "status": SessionStatus.FAILED,
                    "pending_approval": None,
                }
            )
        self._storage.commit_step(
            checkpoint=latest,
            events=(
                LedgerEventInput(
                    event_type=EventType.SESSION_FAILED,
                    payload={
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                ),
            ),
        )

    async def _run_new_task(
        self,
        *,
        session_id: str,
        task: str,
        max_turns: int,
        max_tool_calls: int,
        max_context_tokens: int | None,
    ) -> None:
        async with self._create_sandbox(session_id) as sandbox:
            runtime = self._build_runtime(
                sandbox=sandbox,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_context_tokens=max_context_tokens,
            )
            await runtime.start(task, session_id=session_id)

    async def _run_approved_task(
        self,
        *,
        session_id: str,
        reason: str,
        max_turns: int,
        max_tool_calls: int,
        max_context_tokens: int | None,
    ) -> None:
        async with self._create_sandbox(session_id) as sandbox:
            runtime = self._build_runtime(
                sandbox=sandbox,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_context_tokens=max_context_tokens,
            )
            await runtime.approve(session_id, reason=reason, continue_run=True)

    async def _run_resumed_task(
        self,
        *,
        session_id: str,
        max_turns: int,
        max_tool_calls: int,
        max_context_tokens: int | None,
    ) -> None:
        async with self._create_sandbox(session_id) as sandbox:
            runtime = self._build_runtime(
                sandbox=sandbox,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_context_tokens=max_context_tokens,
            )
            await runtime.resume(session_id)

    @staticmethod
    def _format_sse(event: LedgerEvent) -> str:
        payload = SSEEventPayload(
            event_id=event.event_id,
            session_id=event.session_id,
            step=event.step,
            sequence=event.sequence,
            event_type=event.event_type,
            payload=event.payload,
            timestamp=event.timestamp,
            token_usage=event.token_usage,
        )
        return (
            f"id: {event.sequence}\n"
            f"event: {event.event_type.value}\n"
            f"data: {payload.model_dump_json()}\n\n"
        )
