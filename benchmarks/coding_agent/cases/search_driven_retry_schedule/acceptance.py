"""Deterministic checks for search-driven shared retry repair."""

import json
import subprocess
import sys
from pathlib import Path

_REQUIRED_TOOLS = frozenset(
    {
        "edit_file",
        "list_files",
        "run_tests",
        "search_text",
    }
)


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


def _successful_tool_names(trace: str) -> frozenset[str]:
    names: set[str] = set()

    for line in trace.splitlines():
        parts = line.split(
            " ",
            2,
        )

        if len(parts) != 3 or parts[1] != "tool_execution_finished":
            continue

        payload = json.loads(parts[2])
        tool_name = payload.get("tool_name")

        if payload.get("outcome") == "succeeded" and isinstance(tool_name, str):
            names.add(tool_name)

    return frozenset(names)


def _verify_behavior(workspace: Path) -> None:
    program = """
from retrying.backoff import exponential_delays
from retrying.notifications import notification_retry_delays
from retrying.orders import order_retry_delays

assert exponential_delays(0) == ()
assert exponential_delays(4) == (1, 2, 4, 8)
assert exponential_delays(3, base_seconds=3) == (3, 6, 12)
assert order_retry_delays(3) == (1, 2, 4)
assert notification_retry_delays(2) == (1, 2)
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


def verify(
    workspace: Path,
    trace: str,
) -> None:
    """Verify shared behavior, exploration steps, and change boundary."""
    _verify_behavior(workspace)
    assert _changed_paths(workspace) == ("retrying/backoff.py",)
    assert _REQUIRED_TOOLS <= _successful_tool_names(trace)


def main() -> int:
    """Run acceptance against one workspace and its trace."""
    if len(sys.argv) != 4:
        print(
            "usage: acceptance.py WORKSPACE ANSWER TRACE",
            file=sys.stderr,
        )
        return 2

    workspace = Path(sys.argv[1]).resolve(
        strict=True,
    )
    trace = Path(sys.argv[3]).read_text(
        encoding="utf-8",
    )
    verify(
        workspace,
        trace,
    )
    print("PASS search_driven_retry_schedule")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
