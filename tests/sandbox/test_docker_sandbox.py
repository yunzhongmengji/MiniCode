"""Tests for DockerSandbox resource limits, command routing, and automatic cleanup."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from minicode.sandbox import (
    DockerSandbox,
    SandboxConfig,
    SandboxError,
    SandboxExecutionResult,
)


class _FakeDockerRunner:
    """Record docker CLI invocations without requiring a live Docker daemon."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.stdins: list[bytes | None] = []

    async def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        stdin_data: bytes | None = None,
    ) -> SandboxExecutionResult:
        _ = (timeout_seconds, max_output_bytes)
        cmd = tuple(command)
        self.commands.append(cmd)
        self.stdins.append(stdin_data)
        if len(cmd) >= 2 and cmd[1] == "run":
            return SandboxExecutionResult(exit_code=0, stdout="cid_123456\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "exec":
            return SandboxExecutionResult(exit_code=0, stdout="ok\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "rm":
            return SandboxExecutionResult(exit_code=0, stdout="cid_123456\n", stderr="")
        return SandboxExecutionResult(exit_code=1, stdout="", stderr="unexpected cmd")


@pytest.mark.asyncio
async def test_docker_sandbox_enforces_limits_and_cleans_up_on_exception(
    tmp_path: Path,
) -> None:
    runner = _FakeDockerRunner()
    config = SandboxConfig(
        image="python:3.12-slim",
        cpu_limit=1.5,
        memory_limit="512m",
        pids_limit=64,
        network_mode="none",
        default_timeout_seconds=15.0,
    )
    sandbox = DockerSandbox(
        session_id="sess_sbx_1",
        workspace_root=tmp_path,
        config=config,
        command_runner=runner,
    )

    with pytest.raises(RuntimeError, match="boom"):
        async with sandbox:
            assert sandbox.container_id == "cid_123456"
            await sandbox.write_file("src/app.py", "x = 1\n")
            await sandbox.run_tests("tests/test_app.py")
            raise RuntimeError("boom")

    assert sandbox.is_running is False

    # 1. Start command must include strict CPU, memory, pids, network=none, and mount.
    start_cmd = runner.commands[0]
    assert start_cmd[:3] == ("docker", "run", "-d")
    assert "--cpus" in start_cmd
    assert start_cmd[start_cmd.index("--cpus") + 1] == "1.5"
    assert "--memory" in start_cmd
    assert start_cmd[start_cmd.index("--memory") + 1] == "512m"
    assert "--network" in start_cmd
    assert start_cmd[start_cmd.index("--network") + 1] == "none"
    assert "--pids-limit" in start_cmd
    assert start_cmd[start_cmd.index("--pids-limit") + 1] == "64"
    assert "no-new-privileges:true" in start_cmd
    assert f"{tmp_path.resolve()}:/workspace:rw" in start_cmd

    # 2. Mutations and pytest must execute inside the container via docker exec.
    exec_cmds = [cmd for cmd in runner.commands if len(cmd) >= 2 and cmd[1] == "exec"]
    assert len(exec_cmds) == 2
    assert "cid_123456" in exec_cmds[0]
    assert exec_cmds[1][-3:] == ("pytest", "-q", "tests/test_app.py")

    # 3. Cleanup must force-remove the container even after an unhandled exception.
    assert runner.commands[-1] == ("docker", "rm", "-f", "cid_123456")


@pytest.mark.asyncio
async def test_docker_sandbox_rejects_path_traversal(tmp_path: Path) -> None:
    runner = _FakeDockerRunner()
    sandbox = DockerSandbox(
        session_id="sess_escape",
        workspace_root=tmp_path,
        command_runner=runner,
    )
    async with sandbox:
        with pytest.raises(SandboxError, match="path traversal"):
            await sandbox.write_file("../escape.py", "bad")
        with pytest.raises(SandboxError, match="absolute path"):
            await sandbox.edit_file("/etc/passwd", "a", "b")
