"""Process execution boundary used by coding tools."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Captured result of one completed process."""

    exit_code: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    """Run one command and capture its result."""

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        """Execute a command."""
        ...


class AsyncioProcessRunner:
    """Execute subprocesses without using a shell."""

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        """Run one process and capture its output."""

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise

        exit_code = process.returncode

        if exit_code is None:
            raise RuntimeError("process ended without an exit code")

        return ProcessResult(
            exit_code=exit_code,
            stdout=stdout.decode(
                "utf-8",
                errors="replace",
            ),
            stderr=stderr.decode(
                "utf-8",
                errors="replace",
            ),
        )
