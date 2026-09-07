import asyncio
import sys
from pathlib import Path

import pytest

from minicode.tools.process import (
    AsyncioProcessRunner,
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
