import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "search_driven_retry_schedule"
)
_SUCCESSFUL_TRACE = """Trace run_001
001 tool_execution_finished {"outcome":"succeeded","tool_name":"list_files"}
002 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}
003 tool_execution_finished {"outcome":"succeeded","tool_name":"edit_file"}
004 tool_execution_finished {"outcome":"succeeded","tool_name":"run_tests"}
"""


def _initialize_repository(workspace: Path) -> None:
    subprocess.run(
        ("git", "init", "-q"),
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ("git", "add", "."),
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=MiniCode Test",
            "-c",
            "user.email=minicode@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
        cwd=workspace,
        check=True,
    )


def _run_acceptance(
    workspace: Path,
    answer_path: Path,
    trace_path: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(_CASE_ROOT / "acceptance.py"),
            str(workspace),
            str(answer_path),
            str(trace_path),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def test_search_driven_case_rejects_bug_and_accepts_shared_fix(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(
        _CASE_ROOT / "workspace",
        workspace,
    )
    _initialize_repository(workspace)
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    answer_path.write_text("Fixed shared backoff.", encoding="utf-8")
    trace_path.write_text(_SUCCESSFUL_TRACE, encoding="utf-8")

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    implementation_path = workspace / "retrying" / "backoff.py"
    original = implementation_path.read_text(encoding="utf-8")
    fixed = original.replace(
        "        for attempt in range(\n            1,\n            attempts + 1,\n        )",
        "        for attempt in range(attempts)",
    )
    assert fixed != original
    implementation_path.write_text(fixed, encoding="utf-8")

    acceptance = _run_acceptance(
        workspace,
        answer_path,
        trace_path,
    )

    assert acceptance.returncode == 0, acceptance.stderr
    assert acceptance.stdout.strip() == "PASS search_driven_retry_schedule"
