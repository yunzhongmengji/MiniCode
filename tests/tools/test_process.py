import asyncio
import sys
from pathlib import Path

import pytest

from minicode.tools.process import (
    AsyncioProcessRunner,
    ProcessOutputLimitError,
)


@pytest.mark.asyncio
async def test_asyncio_process_runner_captures_process_result(
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "child.py"
    script_path.write_text(
        (
            "import os\n"
            "import sys\n"
            "\n"
            "print(os.getcwd())\n"
            "print('warning', file=sys.stderr)\n"
        ),
        encoding="utf-8",
    )

    runner = AsyncioProcessRunner()

    result = await runner.run(
        (
            sys.executable,
            "child.py",
        ),
        cwd=tmp_path,
        timeout_seconds=1.0,
    )

    assert result.exit_code == 0
    assert result.stdout == (f"{tmp_path}\n")
    assert result.stderr == "warning\n"


@pytest.mark.asyncio
async def test_asyncio_process_runner_does_not_inherit_secret_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "inspect_environment.py"
    script_path.write_text(
        (
            "import os\n"
            "\n"
            "print('DASHSCOPE_API_KEY' in os.environ)\n"
            "print('PATH' in os.environ)\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "DASHSCOPE_API_KEY",
        "test-secret-not-for-child",
    )
    runner = AsyncioProcessRunner()

    result = await runner.run(
        (
            sys.executable,
            "inspect_environment.py",
        ),
        cwd=tmp_path,
        timeout_seconds=1.0,
    )

    assert result.stdout == "False\nTrue\n"


@pytest.mark.asyncio
async def test_asyncio_process_runner_stops_process_when_output_exceeds_limit(
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "noisy_child.py"
    completed_path = tmp_path / "completed.txt"
    script_path.write_text(
        (
            "import sys\n"
            "import time\n"
            "from pathlib import Path\n"
            "\n"
            "sys.stdout.write('x' * 100_000)\n"
            "sys.stdout.flush()\n"
            "time.sleep(0.2)\n"
            "Path('completed.txt').write_text(\n"
            "    'completed',\n"
            "    encoding='utf-8',\n"
            ")\n"
        ),
        encoding="utf-8",
    )
    runner = AsyncioProcessRunner(
        max_output_bytes=10,
    )

    with pytest.raises(
        ProcessOutputLimitError,
        match="process stdout exceeds the 10-byte limit",
    ):
        await runner.run(
            (
                sys.executable,
                "noisy_child.py",
            ),
            cwd=tmp_path,
            timeout_seconds=1.0,
        )

    assert not completed_path.exists()


@pytest.mark.asyncio
async def test_asyncio_process_runner_kills_timed_out_process(
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "slow_child.py"
    marker_path = tmp_path / "completed.txt"

    script_path.write_text(
        (
            "import time\n"
            "from pathlib import Path\n"
            "\n"
            "time.sleep(0.2)\n"
            "Path('completed.txt').write_text(\n"
            "    'completed',\n"
            "    encoding='utf-8',\n"
            ")\n"
        ),
        encoding="utf-8",
    )

    runner = AsyncioProcessRunner()

    with pytest.raises(
        TimeoutError,
    ):
        await runner.run(
            (
                sys.executable,
                "slow_child.py",
            ),
            cwd=tmp_path,
            timeout_seconds=0.01,
        )

    await asyncio.sleep(0.25)

    assert not marker_path.exists()


@pytest.mark.asyncio
async def test_asyncio_process_runner_kills_cancelled_process(
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "cancelled_child.py"
    started_path = tmp_path / "started.txt"
    completed_path = tmp_path / "completed.txt"
    script_path.write_text(
        (
            "import time\n"
            "from pathlib import Path\n"
            "\n"
            "Path('started.txt').write_text(\n"
            "    'started',\n"
            "    encoding='utf-8',\n"
            ")\n"
            "time.sleep(0.2)\n"
            "Path('completed.txt').write_text(\n"
            "    'completed',\n"
            "    encoding='utf-8',\n"
            ")\n"
        ),
        encoding="utf-8",
    )
    runner = AsyncioProcessRunner()
    task = asyncio.create_task(
        runner.run(
            (
                sys.executable,
                "cancelled_child.py",
            ),
            cwd=tmp_path,
            timeout_seconds=1.0,
        )
    )

    for _ in range(100):
        if started_path.exists():
            break
        await asyncio.sleep(0.01)

    assert started_path.exists()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.25)

    assert not completed_path.exists()
