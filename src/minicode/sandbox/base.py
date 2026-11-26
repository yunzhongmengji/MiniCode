"""Base protocols, configuration, and errors for isolated execution sandboxes."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class SandboxError(RuntimeError):
    """Base error for sandbox lifecycle or execution failures."""


class SandboxTimeoutError(SandboxError):
    """Raised when a sandboxed command exceeds its execution timeout."""


class SandboxConfig(BaseModel):
    """Resource and security limits enforced on each Docker sandbox container."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image: str = Field(default="python:3.12-slim", min_length=1)
    cpu_limit: float = Field(default=1.0, gt=0)
    memory_limit: str = Field(default="512m", min_length=2)
    pids_limit: int = Field(default=128, gt=0)
    network_mode: str = Field(default="none", min_length=1)
    container_workdir: str = Field(default="/workspace", min_length=1)
    default_timeout_seconds: float = Field(default=30.0, gt=0)
    max_output_bytes: int = Field(default=1_000_000, gt=0)
    docker_binary: str = Field(default="docker", min_length=1)


class SandboxExecutionResult(BaseModel):
    """Captured output of one command executed inside a sandbox."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxCommandRunner(Protocol):
    """Low-level async subprocess boundary used by DockerSandbox."""

    async def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        stdin_data: bytes | None = None,
    ) -> SandboxExecutionResult:
        """Execute a host CLI command (e.g. docker) without a shell."""
        ...


class AsyncioSandboxCommandRunner:
    """Execute host docker CLI invocations safely via asyncio subprocess."""

    async def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        stdin_data: bytes | None = None,
    ) -> SandboxExecutionResult:
        """Run one CLI command with hard timeout and bounded output capture."""
        if not command:
            raise ValueError("command must not be empty")

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                raw_stdout, raw_stderr = await process.communicate(input=stdin_data)
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise SandboxTimeoutError(
                f"command timed out after {timeout_seconds}s: {command[0]}"
            ) from error
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        stdout = raw_stdout[:max_output_bytes].decode("utf-8", errors="replace")
        stderr = raw_stderr[:max_output_bytes].decode("utf-8", errors="replace")
        exit_code = process.returncode if process.returncode is not None else -1
        return SandboxExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )
