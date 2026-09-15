"""Process execution boundary used by coding tools."""

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_ALLOWED_ENVIRONMENT_VARIABLES = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
)
_DEFAULT_MAX_OUTPUT_BYTES = 1_000_000


def _subprocess_environment() -> dict[str, str]:
    """Copy only operating-system variables required by child processes."""
    return {
        name: os.environ[name]
        for name in _ALLOWED_ENVIRONMENT_VARIABLES
        if name in os.environ
    }


class ProcessOutputLimitError(RuntimeError):
    """Raised when one child-process output stream exceeds its byte limit."""

    def __init__(
        self,
        *,
        stream_name: str,
        max_bytes: int,
    ) -> None:
        self.stream_name = stream_name
        self.max_bytes = max_bytes
        super().__init__(f"process {stream_name} exceeds the {max_bytes}-byte limit")


async def _read_limited_stream(
    stream: asyncio.StreamReader,
    *,
    stream_name: str,
    max_bytes: int,
) -> bytes:
    """Read one stream without retaining more than its configured limit."""
    output = bytearray()

    while True:
        remaining_bytes = max_bytes - len(output)
        chunk = await stream.read(
            min(
                64 * 1024,
                remaining_bytes + 1,
            )
        )

        if not chunk:
            break

        if len(chunk) > remaining_bytes:
            raise ProcessOutputLimitError(
                stream_name=stream_name,
                max_bytes=max_bytes,
            )

        output.extend(chunk)

    return bytes(output)


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

    def __init__(
        self,
        *,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if type(max_output_bytes) is not int:
            raise TypeError("max_output_bytes must be an integer")

        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero")

        self._max_output_bytes = max_output_bytes

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
            env=_subprocess_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_stream = process.stdout
        stderr_stream = process.stderr

        if stdout_stream is None or stderr_stream is None:
            raise RuntimeError("process output pipes were not created")

        stdout_task = asyncio.create_task(
            _read_limited_stream(
                stdout_stream,
                stream_name="stdout",
                max_bytes=self._max_output_bytes,
            )
        )
        stderr_task = asyncio.create_task(
            _read_limited_stream(
                stderr_stream,
                stream_name="stderr",
                max_bytes=self._max_output_bytes,
            )
        )
        output_tasks = (
            stdout_task,
            stderr_task,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(*output_tasks),
                timeout=timeout_seconds,
            )
            await process.wait()
        except (
            TimeoutError,
            asyncio.CancelledError,
            ProcessOutputLimitError,
        ):
            for task in output_tasks:
                task.cancel()

            await asyncio.gather(
                *output_tasks,
                return_exceptions=True,
            )

            if process.returncode is None:
                process.kill()

            await process.wait()
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
