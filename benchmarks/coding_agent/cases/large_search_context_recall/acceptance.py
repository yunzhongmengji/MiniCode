"""Hidden acceptance checks for repair plus historical evidence recall."""

import subprocess
import sys
from pathlib import Path

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


def verify(workspace: Path, answer: str) -> None:
    """Verify behavior, answer evidence, and the allowed change boundary."""
    _verify_behavior(workspace)
    assert _changed_paths(workspace) == ("service_config/timeouts.py",)
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
    verify(workspace, answer)
    print("PASS large_search_context_recall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
