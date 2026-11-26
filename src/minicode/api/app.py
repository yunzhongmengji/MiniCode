"""FastAPI + SSE application exposing MiniCode's recoverable sandboxed runtime."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse

from minicode.api.service import AgentTaskService
from minicode.models.base import Model
from minicode.models.dashscope import (
    DashScopeConfig,
    build_dashscope_client,
    build_dashscope_model,
)
from minicode.runtime.engine import (
    ApprovalPendingError,
    InvalidSessionStateError,
    SessionNotFoundError,
)
from minicode.sandbox.base import SandboxConfig
from minicode.schemas.api import (
    ApproveTaskRequest,
    CreateTaskRequest,
    ReplayResponse,
    TaskResponse,
)
from minicode.storage.store import SqliteRuntimeStorage


def create_app(service: AgentTaskService) -> FastAPI:
    """Build a FastAPI application wired to an AgentTaskService."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await service.shutdown()

    app = FastAPI(
        title="MiniCode Agent Runtime API",
        version="0.2.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/tasks",
        response_model=TaskResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_task(request: CreateTaskRequest) -> TaskResponse:
        try:
            return await service.create_task(request)
        except InvalidSessionStateError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

    @app.get("/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str) -> TaskResponse:
        try:
            return service.get_task(task_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.get("/tasks/{task_id}/stream")
    async def stream_task_events(task_id: str) -> StreamingResponse:
        return StreamingResponse(
            service.stream_events(task_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/tasks/{task_id}/approve",
        response_model=TaskResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def approve_task(
        task_id: str,
        request: ApproveTaskRequest,
    ) -> TaskResponse:
        try:
            return await service.approve_task(task_id, request)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except InvalidSessionStateError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

    @app.post(
        "/tasks/{task_id}/resume",
        response_model=TaskResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def resume_task(task_id: str) -> TaskResponse:
        try:
            return await service.resume_task(task_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ApprovalPendingError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except InvalidSessionStateError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

    @app.get("/tasks/{task_id}/replay", response_model=ReplayResponse)
    async def replay_task(task_id: str) -> ReplayResponse:
        try:
            session_replay = service.get_replay(task_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return ReplayResponse(
            session_id=session_replay.session_id,
            status=session_replay.status,
            total_steps=session_replay.total_steps,
            total_input_tokens=session_replay.total_input_tokens,
            total_output_tokens=session_replay.total_output_tokens,
            entries=[entry.model_dump(mode="json") for entry in session_replay.entries],
            rendered_text=session_replay.render_text(),
        )

    return app


def create_default_app() -> FastAPI:
    """Factory used by uvicorn --factory minicode.api.app:create_default_app."""
    workspace_root = Path(os.environ.get("MINICODE_WORKSPACE", os.getcwd())).resolve()
    db_path = Path(
        os.environ.get(
            "MINICODE_DB_PATH",
            str(workspace_root / ".minicode" / "runtime.sqlite3"),
        )
    )
    sandbox_config = SandboxConfig(
        image=os.environ.get("MINICODE_SANDBOX_IMAGE", "python:3.12-slim"),
        cpu_limit=float(os.environ.get("MINICODE_SANDBOX_CPUS", "1.0")),
        memory_limit=os.environ.get("MINICODE_SANDBOX_MEMORY", "512m"),
        network_mode="none",
        default_timeout_seconds=float(
            os.environ.get("MINICODE_SANDBOX_TIMEOUT", "30.0")
        ),
    )

    def _build_model() -> Model:
        config = DashScopeConfig.from_environment(os.environ)
        client = build_dashscope_client(config)
        return build_dashscope_model(config, client=client)

    storage = SqliteRuntimeStorage(db_path)
    service = AgentTaskService(
        storage=storage,
        workspace_root=workspace_root,
        model_factory=_build_model,
        sandbox_config=sandbox_config,
    )
    return create_app(service)
