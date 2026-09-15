import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REPAIR_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "large_search_context_repair"
)
_RECALL_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "large_search_context_recall"
)
_SUCCESSFUL_TRACE = """Trace run_001
001 tool_execution_finished {"outcome":"succeeded","tool_name":"list_files"}
002 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}
003 tool_execution_finished {"outcome":"succeeded","tool_name":"read_file"}
004 tool_execution_finished {"outcome":"succeeded","tool_name":"edit_file"}
005 tool_execution_finished {"outcome":"succeeded","tool_name":"run_tests"}
"""
_CORRECT_ANSWER = (
    "Fixed and tested the shared timeout.\n"
    "Evidence summary: 25 clients; "
    "first=accounting-ledger; last=transaction-journal.\n"
)


def _initialize_repository(workspace: Path) -> None:
    subprocess.run(("git", "init", "-q"), cwd=workspace, check=True)
    subprocess.run(("git", "add", "."), cwd=workspace, check=True)
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
            str(_RECALL_CASE_ROOT / "acceptance.py"),
            str(workspace),
            str(answer_path),
            str(trace_path),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def _workspace_files(case_root: Path) -> dict[str, bytes]:
    workspace = case_root / "workspace"
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def test_recall_case_keeps_the_repair_workspace_identical() -> None:
    assert _workspace_files(_RECALL_CASE_ROOT) == _workspace_files(_REPAIR_CASE_ROOT)


def test_recall_case_requires_repair_and_exact_early_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(_RECALL_CASE_ROOT / "workspace", workspace)
    _initialize_repository(workspace)
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(_SUCCESSFUL_TRACE, encoding="utf-8")
    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    implementation_path = workspace / "service_config" / "timeouts.py"
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8").replace(
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
        ),
        encoding="utf-8",
    )
    answer_path.write_text(
        "Fixed, but I omitted the requested evidence.\n",
        encoding="utf-8",
    )

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")
    acceptance = _run_acceptance(workspace, answer_path, trace_path)

    assert acceptance.returncode == 0, acceptance.stderr
    assert acceptance.stdout.strip() == "PASS large_search_context_recall"


def test_recall_case_rejects_repeated_search(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(_RECALL_CASE_ROOT / "workspace", workspace)
    _initialize_repository(workspace)
    implementation_path = workspace / "service_config" / "timeouts.py"
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8").replace(
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
        ),
        encoding="utf-8",
    )
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")
    trace_path.write_text(
        _SUCCESSFUL_TRACE
        + '006 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}\n',
        encoding="utf-8",
    )

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0
