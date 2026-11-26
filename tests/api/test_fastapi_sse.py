"""End-to-end tests for FastAPI + SSE task streaming, approval, resume, and replay."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest

from minicode.api import AgentTaskService, create_app
from minicode.models import ModelResponse, ScriptedModel
from minicode.sandbox import DockerSandbox, SandboxConfig, SandboxExecutionResult
from minicode.schemas import (
    MessageRecord,
    MessageRole,
    SessionCheckpoint,
    SessionStatus,
    TokenUsage,
    ToolCallRecord,
)
from minicode.storage import SqliteRuntimeStorage


class _RecordingDockerRunner:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.removed: list[str] = []
        self.execs: list[tuple[str, ...]] = []

    async def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        stdin_data: bytes | None = None,
    ) -> SandboxExecutionResult:
        _ = (timeout_seconds, max_output_bytes, stdin_data)
        cmd = tuple(command)
        if len(cmd) >= 2 and cmd[1] == "run":
            cid = f"cid_{len(self.started) + 1}"
            self.started.append(cid)
            return SandboxExecutionResult(exit_code=0, stdout=f"{cid}\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "exec":
            self.execs.append(cmd)
            return SandboxExecutionResult(exit_code=0, stdout="edited app.py\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "rm":
            self.removed.append(cmd[-1])
            return SandboxExecutionResult(exit_code=0, stdout=f"{cmd[-1]}\n", stderr="")
        return SandboxExecutionResult(exit_code=0, stdout="", stderr="")


def _parse_sse_frames(body: str) -> list[tuple[str, dict[str, object]]]:
    frames: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_raw = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_raw = line[len("data: ") :]
        if event_name and data_raw:
            frames.append((event_name, json.loads(data_raw)))
    return frames


@pytest.mark.asyncio
async def test_fastapi_sse_lifecycle_with_approval_and_replay(tmp_path: Path) -> None:
    """Test POST /tasks -> SSE stream -> POST /approve -> SSE stream -> GET /replay."""
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    db_path = tmp_path / "api.sqlite3"
    docker_runner = _RecordingDockerRunner()

    # Model turn 1 proposes high-risk edit_file; turn 2 finishes after approval.
    responses_queue = [
        ScriptedModel(
            (
                ModelResponse(
                    content="I will edit app.py inside the sandbox.",
                    tool_calls=(
                        ToolCallRecord(
                            call_id="edit_1",
                            name="edit_file",
                            arguments={
                                "path": "app.py",
                                "old_text": "value = 1",
                                "new_text": "value = 2",
                            },
                        ),
                    ),
                    usage=TokenUsage(input_tokens=60, output_tokens=20),
                ),
            )
        ),
        ScriptedModel(
            (
                ModelResponse(
                    content="Updated app.py successfully in sandbox.",
                    usage=TokenUsage(input_tokens=90, output_tokens=15),
                ),
            )
        ),
    ]

    def model_factory() -> ScriptedModel:
        return responses_queue.pop(0)

    def sandbox_factory(session_id: str, workspace_root: Path) -> DockerSandbox:
        return DockerSandbox(
            session_id=session_id,
            workspace_root=workspace_root,
            config=SandboxConfig(network_mode="none", memory_limit="512m"),
            command_runner=docker_runner,
        )

    storage = SqliteRuntimeStorage(db_path)
    service = AgentTaskService(
        storage=storage,
        workspace_root=tmp_path,
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
    )
    app = create_app(service)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            # 1. Create task (returns 202 immediately).
            create_res = await client.post(
                "/tasks",
                json={"task": "Update value in app.py", "session_id": "task_sse_1"},
            )
            assert create_res.status_code == 202
            assert create_res.json()["task_id"] == "task_sse_1"

            # 2. Stream SSE until task pauses for high-risk approval.
            stream1 = await client.get("/tasks/task_sse_1/stream")
            assert stream1.status_code == 200
            frames1 = _parse_sse_frames(stream1.text)
            event_names1 = [name for name, _ in frames1]
            assert "session_started" in event_names1
            assert "reasoning_completed" in event_names1
            assert "approval_required" in event_names1
            assert "session_paused" in event_names1

            # 3. Approve the high-risk edit_file call.
            approve_res = await client.post(
                "/tasks/task_sse_1/approve",
                json={"decision": "approve", "reason": "verified diff"},
            )
            assert approve_res.status_code == 202

            # 4. Stream SSE until completion.
            stream2 = await client.get("/tasks/task_sse_1/stream")
            assert stream2.status_code == 200
            frames2 = _parse_sse_frames(stream2.text)
            event_names2 = [name for name, _ in frames2]
            assert "approval_decided" in event_names2
            assert "tool_executed" in event_names2
            assert "session_completed" in event_names2

            # 5. Read-only replay endpoint returns complete audit timeline.
            replay_res = await client.get("/tasks/task_sse_1/replay")
            assert replay_res.status_code == 200
            replay_json = replay_res.json()
            assert replay_json["status"] == "completed"
            assert replay_json["total_input_tokens"] == 150
            assert "approval: approve" in replay_json["rendered_text"]

            # 6. Every started Docker container was cleanly removed.
            assert len(docker_runner.started) == 2
            assert docker_runner.removed == docker_runner.started
            assert len(docker_runner.execs) == 1
    finally:
        await service.shutdown()
        storage.close()


@pytest.mark.asyncio
async def test_fastapi_resume_endpoint_recovers_interrupted_task(tmp_path: Path) -> None:
    """POST /tasks/{id}/resume restarts an interrupted RUNNING checkpoint."""
    db_path = tmp_path / "api_resume.sqlite3"
    docker_runner = _RecordingDockerRunner()

    storage = SqliteRuntimeStorage(db_path)
    # Seed an interrupted RUNNING checkpoint as if a previous server crashed.
    storage.commit_step(
        checkpoint=SessionCheckpoint(
            session_id="task_interrupted",
            step=1,
            status=SessionStatus.RUNNING,
            history=(MessageRecord(role=MessageRole.USER, content="Finish task"),),
            turns_used=0,
        )
    )

    service = AgentTaskService(
        storage=storage,
        workspace_root=tmp_path,
        model_factory=lambda: ScriptedModel(
            (ModelResponse(content="Recovered and finished."),)
        ),
        sandbox_factory=lambda sid, root: DockerSandbox(
            session_id=sid,
            workspace_root=root,
            command_runner=docker_runner,
        ),
    )
    app = create_app(service)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            res = await client.post("/tasks/task_interrupted/resume")
            assert res.status_code == 202

            stream = await client.get("/tasks/task_interrupted/stream")
            assert stream.status_code == 200
            frames = _parse_sse_frames(stream.text)
            event_names = [name for name, _ in frames]
            assert "session_resumed" in event_names
            assert "session_completed" in event_names

            task_res = await client.get("/tasks/task_interrupted")
            assert task_res.status_code == 200
            assert task_res.json()["status"] == "completed"
            assert task_res.json()["final_answer"] == "Recovered and finished."
            assert docker_runner.removed == docker_runner.started
    finally:
        await service.shutdown()
        storage.close()
