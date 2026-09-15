"""Hidden deterministic acceptance checks for large search context repair."""

import json
import subprocess
import sys
from pathlib import Path

_REQUIRED_TOOLS = frozenset(
    {
        "edit_file",
        "list_files",
        "read_file",
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
        parts = line.split(" ", 2)

        if len(parts) != 3 or parts[1] != "tool_execution_finished":
            continue

        payload = json.loads(parts[2])
        tool_name = payload.get("tool_name")

        if payload.get("outcome") == "succeeded" and isinstance(tool_name, str):
            names.add(tool_name)

    return frozenset(names)


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


def verify(workspace: Path, trace: str) -> None:
    """Verify shared behavior, exploration steps, and change boundary."""
    _verify_behavior(workspace)
    assert _changed_paths(workspace) == ("service_config/timeouts.py",)
    assert _REQUIRED_TOOLS <= _successful_tool_names(trace)


def main() -> int:
    """Run acceptance against one workspace and its trace."""
    if len(sys.argv) != 4:
        print(
            "usage: acceptance.py WORKSPACE ANSWER TRACE",
            file=sys.stderr,
        )
        return 2

    workspace = Path(sys.argv[1]).resolve(strict=True)
    trace = Path(sys.argv[3]).read_text(encoding="utf-8")
    verify(workspace, trace)
    print("PASS large_search_context_repair")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
