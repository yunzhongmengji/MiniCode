"""Hidden acceptance checks for repair plus historical evidence recall."""

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
_REQUIRED_EVIDENCE_SUMMARY = (
    "Evidence summary: 25 clients; first=accounting-ledger; last=transaction-journal."
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
    return frozenset(
        tool_name
        for tool_name in _successful_tool_sequence(trace)
        if isinstance(tool_name, str)
    )


def _successful_tool_sequence(trace: str) -> tuple[str, ...]:
    names: list[str] = []

    for line in trace.splitlines():
        parts = line.split(" ", 2)

        if len(parts) != 3 or parts[1] != "tool_execution_finished":
            continue

        payload = json.loads(parts[2])
        tool_name = payload.get("tool_name")

        if payload.get("outcome") == "succeeded" and isinstance(tool_name, str):
            names.append(tool_name)

    return tuple(names)


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


def verify(workspace: Path, answer: str, trace: str) -> None:
    """Verify behavior, answer evidence, tool process, and change boundary."""
    _verify_behavior(workspace)
    assert _changed_paths(workspace) == ("service_config/timeouts.py",)
    assert _REQUIRED_TOOLS <= _successful_tool_names(trace)
    assert _successful_tool_sequence(trace).count("search_text") == 1
    assert _REQUIRED_EVIDENCE_SUMMARY in answer.splitlines()


def main() -> int:
    """Run acceptance against one workspace, answer, and trace."""
    if len(sys.argv) != 4:
        print(
            "usage: acceptance.py WORKSPACE ANSWER TRACE",
            file=sys.stderr,
        )
        return 2

    workspace = Path(sys.argv[1]).resolve(strict=True)
    answer = Path(sys.argv[2]).read_text(encoding="utf-8")
    trace = Path(sys.argv[3]).read_text(encoding="utf-8")
    verify(workspace, answer, trace)
    print("PASS large_search_context_recall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
