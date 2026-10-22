"""Project-scoped candidate reads, without memory admission or model calls."""

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from minicode import cli
from minicode.core.checkpoints import RunCheckpoint
from minicode.core.file_checkpoint_store import (
    FileCheckpointStore,
    workspace_checkpoint_root,
)
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.memory.test_target import load_test_target_candidate
from minicode.workspace import Workspace


def _workspace(root: Path) -> Workspace:
    (root / "tests").mkdir(parents=True)
    return Workspace(root)


def _save(
    workspace: Workspace,
    state_home: Path,
    *,
    output: str = "1 passed",
    completed: bool = True,
    is_error: bool = False,
) -> Path:
    root = workspace_checkpoint_root(
        workspace_root=workspace.root, state_home=state_home
    )
    FileCheckpointStore(root).save(
        RunCheckpoint(
            run_id="same_run",
            message_history=(
                ToolCall(call_id="tests_1", name="run_tests", arguments={}),
                ToolResult(call_id="tests_1", output=output, is_error=is_error),
            ),
            turns_used=2,
            tool_calls_used=1,
            is_completed=completed,
        )
    )
    return root


def test_load_reads_saved_source_without_changing_it(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    root = _save(workspace, state_home)
    source = next(root.glob("*.json"))
    before = source.read_bytes()

    candidate = load_test_target_candidate(
        workspace=workspace, state_home=state_home, run_id="same_run", call_id="tests_1"
    )

    assert candidate.workspace_root == workspace.root
    assert candidate.target_path == "tests"
    assert candidate.source_run_id == "same_run"
    assert candidate.source_call_id == "tests_1"
    assert candidate.source_result_sha256 == sha256(b"1 passed").hexdigest()
    assert source.read_bytes() == before
    assert list(root.iterdir()) == [source]
    assert list(workspace.root.iterdir()) == [workspace.root / "tests"]


def test_same_run_and_call_ids_do_not_mix_project_sources(tmp_path: Path) -> None:
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")
    state_home = tmp_path / "state"
    first_root = _save(first, state_home, output="first project output")
    second_root = _save(second, state_home, output="second project output")

    assert first_root != second_root
    for workspace, output in (
        (first, "first project output"),
        (second, "second project output"),
    ):
        candidate = load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )
        assert candidate.workspace_root == workspace.root
        assert candidate.source_result_sha256 == sha256(output.encode()).hexdigest()


def test_other_project_source_is_not_a_fallback(tmp_path: Path) -> None:
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")
    state_home = tmp_path / "state"
    _save(first, state_home)

    with pytest.raises(FileNotFoundError, match="no checkpoint directory"):
        load_test_target_candidate(
            workspace=second,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )

    assert not workspace_checkpoint_root(
        workspace_root=second.root, state_home=state_home
    ).exists()


def test_missing_state_is_not_created(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "absent-state"
    with pytest.raises(FileNotFoundError, match="no checkpoint directory"):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )
    assert not state_home.exists()


def test_missing_run_does_not_use_another_run(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    _save(workspace, state_home)
    with pytest.raises(FileNotFoundError, match="workspace and run"):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="missing_run",
            call_id="tests_1",
        )


@pytest.mark.parametrize("options", [{"completed": False}, {"is_error": True}])
def test_saved_source_still_must_pass_candidate_checks(tmp_path: Path, options) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    _save(workspace, state_home, **options)
    with pytest.raises(ValueError):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )


def test_unknown_call_is_not_replaced_with_a_success(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    _save(workspace, state_home)
    with pytest.raises(LookupError, match="tool call not found"):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="other_call",
        )


@pytest.mark.parametrize("damage", ["invalid_json", "wrong_run_id"])
def test_damaged_source_is_rejected_not_repaired(tmp_path: Path, damage: str) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    root = _save(workspace, state_home)
    source = next(root.glob("*.json"))
    if damage == "invalid_json":
        source.write_text("{broken", encoding="utf-8")
    else:
        document = json.loads(source.read_text(encoding="utf-8"))
        document["run_id"] = "another_run"
        source.write_text(json.dumps(document), encoding="utf-8")
    before = source.read_bytes()

    with pytest.raises(ValueError):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )
    assert source.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory permissions")
def test_shared_source_directory_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    root = _save(workspace, state_home)
    root.chmod(0o755)
    with pytest.raises(PermissionError, match="group-accessible"):
        load_test_target_candidate(
            workspace=workspace,
            state_home=state_home,
            run_id="same_run",
            call_id="tests_1",
        )


def test_workspace_alias_uses_same_source_directory(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    _save(workspace, state_home)
    alias = tmp_path / "alias"
    alias.symlink_to(workspace.root, target_is_directory=True)
    candidate = load_test_target_candidate(
        workspace=Workspace(alias),
        state_home=state_home,
        run_id="same_run",
        call_id="tests_1",
    )
    assert candidate.workspace_root == workspace.root


def test_source_directory_matches_cli_and_preserves_existing_layout(tmp_path: Path):
    workspace = _workspace(tmp_path / "project")
    state_home = tmp_path / "state"
    expected = (
        state_home
        / "minicode"
        / "checkpoints"
        / sha256(str(workspace.root).encode()).hexdigest()
    )
    assert (
        workspace_checkpoint_root(workspace_root=workspace.root, state_home=state_home)
        == cli._checkpoint_root(workspace.root, {"XDG_STATE_HOME": str(state_home)})
        == expected
    )


@pytest.mark.parametrize("field", ["workspace_root", "state_home"])
def test_source_directory_rejects_relative_roots(tmp_path: Path, field: str) -> None:
    values = {"workspace_root": tmp_path, "state_home": tmp_path / "state"}
    values[field] = Path("relative")
    with pytest.raises(ValueError, match=f"{field} must be absolute"):
        workspace_checkpoint_root(**values)
