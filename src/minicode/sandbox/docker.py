"""Docker container sandbox isolating workspace mutations and test execution."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Self
from uuid import uuid4

from minicode.sandbox.base import (
    AsyncioSandboxCommandRunner,
    SandboxCommandRunner,
    SandboxConfig,
    SandboxError,
    SandboxExecutionResult,
)
from minicode.tools.process import ProcessResult

_SAFE_SESSION_RE = re.compile(r"[^a-zA-Z0-9_.-]")

_WRITE_FILE_SCRIPT = """
import json, pathlib, sys
payload = json.loads(sys.stdin.read())
target = pathlib.Path(payload["path"])
if target.exists() and not payload["overwrite"]:
    raise FileExistsError(f"file already exists: {target}")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(payload["content"], encoding="utf-8")
print(f"wrote {len(payload['content'].encode('utf-8'))} bytes to {target}")
"""

_EDIT_FILE_SCRIPT = """
import json, pathlib, sys
payload = json.loads(sys.stdin.read())
target = pathlib.Path(payload["path"])
if not target.is_file():
    raise FileNotFoundError(f"file not found: {target}")
text = target.read_text(encoding="utf-8")
old_text = payload["old_text"]
count = text.count(old_text)
if count == 0:
    raise ValueError("old_text not found in file")
if count > 1:
    raise ValueError(f"old_text matched {count} times; must be unique")
updated = text.replace(old_text, payload["new_text"], 1)
target.write_text(updated, encoding="utf-8")
print(f"edited {target}")
"""


def _normalize_relative_workspace_path(relative_path: str) -> str:
    """Reject absolute paths or parent-directory traversal attempts."""
    if not relative_path or not relative_path.strip():
        raise SandboxError("path must not be blank")
    posix_path = PurePosixPath(relative_path)
    if posix_path.is_absolute():
        raise SandboxError(f"absolute path is not allowed: {relative_path}")
    if ".." in posix_path.parts:
        raise SandboxError(f"path traversal is not allowed: {relative_path}")
    return posix_path.as_posix()


class DockerSandbox:
    """Manage one isolated Docker container per agent task session."""

    def __init__(
        self,
        *,
        session_id: str,
        workspace_root: Path,
        config: SandboxConfig | None = None,
        command_runner: SandboxCommandRunner | None = None,
    ) -> None:
        if not session_id.strip():
            raise ValueError("session_id must not be blank")
        self._session_id = session_id
        self._workspace_root = workspace_root.resolve()
        self._config = SandboxConfig() if config is None else config
        self._runner: SandboxCommandRunner = (
            AsyncioSandboxCommandRunner()
            if command_runner is None
            else command_runner
        )
        sanitized = _SAFE_SESSION_RE.sub("-", session_id)[:32]
        self._container_name = f"minicode-sbx-{sanitized}-{uuid4().hex[:8]}"
        self._container_id: str | None = None

    @property
    def container_name(self) -> str:
        """Return the deterministic container name for this session."""
        return self._container_name

    @property
    def container_id(self) -> str | None:
        """Return the active container ID once started."""
        return self._container_id

    @property
    def config(self) -> SandboxConfig:
        """Return active sandbox resource and security limits."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Return True while the container has been started and not cleaned up."""
        return self._container_id is not None

    def build_start_command(self) -> tuple[str, ...]:
        """Build the hardened docker run command with CPU/memory/network limits."""
        cfg = self._config
        return (
            cfg.docker_binary,
            "run",
            "-d",
            "--rm",
            "--name",
            self._container_name,
            "--cpus",
            str(cfg.cpu_limit),
            "--memory",
            cfg.memory_limit,
            "--memory-swap",
            cfg.memory_limit,
            "--pids-limit",
            str(cfg.pids_limit),
            "--network",
            cfg.network_mode,
            "--security-opt",
            "no-new-privileges:true",
            "-v",
            f"{self._workspace_root}:{cfg.container_workdir}:rw",
            "-w",
            cfg.container_workdir,
            cfg.image,
            "sleep",
            "infinity",
        )

    async def start(self) -> str:
        """Start the isolated session container."""
        if self._container_id is not None:
            return self._container_id

        result = await self._runner.run(
            self.build_start_command(),
            timeout_seconds=self._config.default_timeout_seconds,
            max_output_bytes=self._config.max_output_bytes,
        )
        if result.exit_code != 0:
            raise SandboxError(
                f"failed to start Docker sandbox container: {result.stderr.strip()}"
            )
        container_id = result.stdout.strip() or self._container_name
        self._container_id = container_id
        return container_id

    async def exec(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin_data: bytes | None = None,
    ) -> SandboxExecutionResult:
        """Execute a command inside the running container with timeout enforcement."""
        if not command:
            raise ValueError("command must not be empty")
        if self._container_id is None:
            await self.start()
        assert self._container_id is not None

        effective_timeout = (
            self._config.default_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        docker_cmd = (
            self._config.docker_binary,
            "exec",
            "-i",
            "-w",
            self._config.container_workdir,
            self._container_id,
            *command,
        )
        return await self._runner.run(
            docker_cmd,
            timeout_seconds=effective_timeout,
            max_output_bytes=self._config.max_output_bytes,
            stdin_data=stdin_data,
        )

    async def write_file(
        self,
        relative_path: str,
        content: str,
        *,
        overwrite: bool = False,
    ) -> str:
        """Create or write a workspace file inside the container."""
        clean_path = _normalize_relative_workspace_path(relative_path)
        payload = json.dumps(
            {
                "path": f"{self._config.container_workdir}/{clean_path}",
                "content": content,
                "overwrite": overwrite,
            }
        ).encode("utf-8")
        result = await self.exec(
            ("python3", "-c", _WRITE_FILE_SCRIPT),
            stdin_data=payload,
        )
        if result.exit_code != 0:
            raise SandboxError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    async def edit_file(
        self,
        relative_path: str,
        old_text: str,
        new_text: str,
    ) -> str:
        """Perform exact-match file editing inside the container."""
        clean_path = _normalize_relative_workspace_path(relative_path)
        payload = json.dumps(
            {
                "path": f"{self._config.container_workdir}/{clean_path}",
                "old_text": old_text,
                "new_text": new_text,
            }
        ).encode("utf-8")
        result = await self.exec(
            ("python3", "-c", _EDIT_FILE_SCRIPT),
            stdin_data=payload,
        )
        if result.exit_code != 0:
            raise SandboxError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    async def run_tests(
        self,
        target: str | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> SandboxExecutionResult:
        """Execute pytest inside the isolated container."""
        command: list[str] = ["pytest", "-q"]
        if target is not None and target.strip():
            command.append(_normalize_relative_workspace_path(target))
        return await self.exec(command, timeout_seconds=timeout_seconds)

    async def cleanup(self) -> None:
        """Force-remove the container unconditionally (safe to call multiple times)."""
        target = self._container_id or self._container_name
        self._container_id = None
        try:
            await self._runner.run(
                (self._config.docker_binary, "rm", "-f", target),
                timeout_seconds=10.0,
                max_output_bytes=65_536,
            )
        except SandboxError:
            return

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.cleanup()


class DockerProcessRunner:
    """Adapt DockerSandbox to MiniCode's ProcessRunner protocol."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        """Execute a command inside the Docker sandbox container."""
        _ = cwd  # Container workdir is fixed to /workspace.
        res = await self._sandbox.exec(command, timeout_seconds=timeout_seconds)
        return ProcessResult(
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
        )
