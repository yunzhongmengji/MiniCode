"""Hidden deterministic acceptance checks for large search context repair."""

import subprocess
import sys
from pathlib import Path


def _changed_paths(workspace: Path) -> tuple[str, ...]:
    result = subprocess.run(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
        ),
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line[3:] for line in result.stdout.splitlines() if line)


def _verify_behavior(workspace: Path) -> None:
    program = """
from service_config.client_registry import CLIENT_REQUEST_TIMEOUTS
from service_config.timeouts import DEFAULT_REQUEST_TIMEOUT_SECONDS

assert DEFAULT_REQUEST_TIMEOUT_SECONDS == 30
assert len(CLIENT_REQUEST_TIMEOUTS) == 25
assert set(CLIENT_REQUEST_TIMEOUTS.values()) == {30}
"""
    subprocess.run(
        (
            sys.executable,
            "-c",
            program,
        ),
        cwd=workspace,
        check=True,
    )


def verify(workspace: Path) -> None:
    """Verify shared behavior and the allowed change boundary."""
    _verify_behavior(workspace)
    assert _changed_paths(workspace) == ("service_config/timeouts.py",)


def main() -> int:
    """Run acceptance against one workspace and its trace."""
    if len(sys.argv) != 4:
        print(
            "usage: acceptance.py WORKSPACE ANSWER TRACE",
            file=sys.stderr,
        )
        return 2

    workspace = Path(sys.argv[1]).resolve(strict=True)
    verify(workspace)
    print("PASS large_search_context_repair")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
