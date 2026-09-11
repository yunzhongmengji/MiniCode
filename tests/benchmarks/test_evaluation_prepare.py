import subprocess
from pathlib import Path

from minicode.evaluation_prepare import (
    prepare_evaluation_workspace,
)


def test_prepares_isolated_workspace_with_clean_git_baseline(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )

    workspace = prepare_evaluation_workspace(
        case_root,
        temporary_root=tmp_path,
    )

    assert workspace.parent == tmp_path
    assert (workspace / "batching.py").is_file()
    assert (workspace / "tests" / "test_batching.py").is_file()
    assert not (workspace / "case.json").exists()
    assert not (workspace / "task.txt").exists()
    assert not (workspace / "acceptance.py").exists()
    assert _git_status(workspace) == ""

    (workspace / "batching.py").write_text(
        "def batches():\n    return []\n",
        encoding="utf-8",
    )

    assert _git_status(workspace) == " M batching.py"


def _git_status(workspace: Path) -> str:
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
    return result.stdout.rstrip()
