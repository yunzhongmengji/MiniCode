"""Single-record persistence with simulated host confirmation, not real adoption."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.file_checkpoint_store import (
    FileCheckpointStore,
    workspace_checkpoint_root,
)
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.memory import store as memory_store
from minicode.memory.store import (
    MAX_MEMORY_RECORD_BYTES,
    confirm_and_save_test_target,
    load_saved_test_target,
)
from minicode.workspace import Workspace


def _checkpoint(
    *, run_id: str = "run_source", output: str = "1 passed"
) -> RunCheckpoint:
    return RunCheckpoint(
        run_id=run_id,
        message_history=(
            ToolCall(call_id="tests_1", name="run_tests", arguments={"path": "tests"}),
            ToolResult(call_id="tests_1", output=output),
        ),
        turns_used=2,
        tool_calls_used=1,
        is_completed=True,
    )


@pytest.fixture
def source(tmp_path: Path) -> tuple[Workspace, Path, FileCheckpointStore]:
    root = tmp_path / "project"
    (root / "tests").mkdir(parents=True)
    workspace = Workspace(root)
    state_home = tmp_path / "state"
    checkpoints = FileCheckpointStore(
        workspace_checkpoint_root(workspace_root=workspace.root, state_home=state_home)
    )
    checkpoints.save(_checkpoint())
    return workspace, state_home, checkpoints


def _save(source, *, answer: str = "yes", run_id: str = "run_source"):
    workspace, state_home, _ = source
    answers = iter(["仅用于该模块的单元测试", answer])
    return confirm_and_save_test_target(
        workspace=workspace,
        state_home=state_home,
        run_id=run_id,
        call_id="tests_1",
        input_reader=lambda: next(answers),
    )


def _record_path(source) -> Path:
    _, state_home, _ = source
    return next((state_home / "minicode" / "memory").glob("*/test_target.json"))


def test_confirmed_record_round_trips_without_copying_history(source) -> None:
    workspace, state_home, checkpoints = source
    before = checkpoints.latest("run_source")
    confirmed = _save(source)
    assert confirmed is not None
    # A fresh Workspace and disk read cannot rely on the returned object.
    loaded = load_saved_test_target(
        workspace=Workspace(workspace.root), state_home=state_home
    )
    assert loaded == confirmed
    document = json.loads(_record_path(source).read_text(encoding="utf-8"))
    assert set(document) == {"schema_version", "confirmation"}
    assert document["schema_version"] == 1
    assert set(document["confirmation"]) == {"candidate", "applies_to"}
    assert "1 passed" not in _record_path(source).read_text(encoding="utf-8")
    assert checkpoints.latest("run_source") == before
    assert list(workspace.root.iterdir()) == [workspace.root / "tests"]
    assert not tuple(_record_path(source).parent.glob("*.tmp"))


def test_record_can_be_read_in_another_process(source) -> None:
    workspace, state_home, _ = source
    _save(source)
    script = (
        "from pathlib import Path; import sys; "
        "from minicode.workspace import Workspace; "
        "from minicode.memory.store import load_saved_test_target; "
        "r=load_saved_test_target(workspace=Workspace(Path(sys.argv[1])), "
        "state_home=Path(sys.argv[2])); "
        "assert r is not None; print(r.candidate.target_path)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(workspace.root), str(state_home)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert completed.stdout.strip() == "tests"


@pytest.mark.parametrize("answer", ["", "no", "true"])
def test_denied_confirmation_creates_no_memory_directory(source, answer: str) -> None:
    workspace, state_home, _ = source
    assert _save(source, answer=answer) is None
    assert not (state_home / "minicode" / "memory").exists()
    assert load_saved_test_target(workspace=workspace, state_home=state_home) is None


@pytest.mark.parametrize("error_type", [EOFError, KeyboardInterrupt])
def test_interrupted_confirmation_creates_no_record(source, error_type) -> None:
    workspace, state_home, _ = source

    def interrupted() -> str:
        raise error_type()

    assert (
        confirm_and_save_test_target(
            workspace=workspace,
            state_home=state_home,
            run_id="run_source",
            call_id="tests_1",
            input_reader=interrupted,
        )
        is None
    )
    assert not (state_home / "minicode" / "memory").exists()


def test_missing_memory_read_does_not_create_state(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    state_home = tmp_path / "missing_state"
    assert (
        load_saved_test_target(workspace=Workspace(root), state_home=state_home) is None
    )
    assert not state_home.exists()


def test_other_project_does_not_read_saved_record(source, tmp_path: Path) -> None:
    _, state_home, _ = source
    _save(source)
    other_root = tmp_path / "other"
    (other_root / "tests").mkdir(parents=True)
    other = Workspace(other_root)
    FileCheckpointStore(
        workspace_checkpoint_root(workspace_root=other.root, state_home=state_home)
    ).save(_checkpoint())
    assert load_saved_test_target(workspace=other, state_home=state_home) is None


def test_record_with_another_workspace_field_is_rejected(source) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["confirmation"]["candidate"]["workspace_root"] = "/another/project"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="another workspace"):
        load_saved_test_target(workspace=workspace, state_home=state_home)


def test_existing_record_is_not_overwritten_or_reconfirmed(source) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    before = path.read_bytes()

    def unexpected_input() -> str:
        pytest.fail("existing record must stop before confirmation")

    with pytest.raises(FileExistsError, match="already saved"):
        confirm_and_save_test_target(
            workspace=workspace,
            state_home=state_home,
            run_id="run_source",
            call_id="tests_1",
            input_reader=unexpected_input,
        )
    assert path.read_bytes() == before


def test_changed_source_after_confirmation_is_rejected_before_publication(
    source, monkeypatch
) -> None:
    _, state_home, checkpoints = source
    original = memory_store.confirm_test_target

    def change_after_confirmation(**kwargs):
        confirmed = original(**kwargs)
        checkpoints.save(_checkpoint(output="2 passed"))
        return confirmed

    monkeypatch.setattr(memory_store, "confirm_test_target", change_after_confirmation)
    with pytest.raises(ValueError, match="source changed"):
        _save(source)
    assert not tuple((state_home / "minicode" / "memory").rglob("test_target.json"))
    assert not tuple((state_home / "minicode" / "memory").rglob("*.tmp"))


def test_source_changed_after_save_is_not_returned_as_valid(source) -> None:
    workspace, state_home, checkpoints = source
    _save(source)
    checkpoints.save(_checkpoint(output="2 passed"))
    with pytest.raises(ValueError, match="source changed"):
        load_saved_test_target(workspace=workspace, state_home=state_home)


def test_missing_source_after_save_is_rejected(source) -> None:
    workspace, state_home, _ = source
    _save(source)
    root = workspace_checkpoint_root(
        workspace_root=workspace.root, state_home=state_home
    )
    next(root.glob("*.json")).unlink()
    with pytest.raises(FileNotFoundError, match="checkpoint found"):
        load_saved_test_target(workspace=workspace, state_home=state_home)


def test_repository_json_is_not_a_memory_source(source) -> None:
    workspace, state_home, _ = source
    (workspace.root / "memory.json").write_text('{"approved":true}', encoding="utf-8")
    assert load_saved_test_target(workspace=workspace, state_home=state_home) is None


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_unsupported_or_non_integer_schema_is_rejected(source, version) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = version
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_saved_test_target(workspace=workspace, state_home=state_home)


@pytest.mark.parametrize(
    "damage", ["invalid_json", "extra_approval", "blank_scope", "missing_version"]
)
def test_bad_record_is_rejected_without_repair(source, damage: str) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    document = json.loads(path.read_text(encoding="utf-8"))
    if damage == "invalid_json":
        path.write_text("{broken", encoding="utf-8")
    else:
        if damage == "extra_approval":
            document["confirmation"]["approved"] = True
        elif damage == "missing_version":
            del document["schema_version"]
        else:
            document["confirmation"]["applies_to"] = " "
        path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        load_saved_test_target(workspace=workspace, state_home=state_home)
    assert path.read_bytes() == before


def test_oversized_record_is_not_parsed(source) -> None:
    workspace, state_home, _ = source
    _save(source)
    _record_path(source).write_bytes(b" " * (MAX_MEMORY_RECORD_BYTES + 1))
    with pytest.raises(ValueError, match="16384-byte"):
        load_saved_test_target(workspace=workspace, state_home=state_home)


def test_oversized_admission_is_not_persisted(source) -> None:
    _, state_home, checkpoints = source
    run_id = "r" * MAX_MEMORY_RECORD_BYTES
    checkpoints.save(_checkpoint(run_id=run_id))
    with pytest.raises(ValueError, match="16384-byte"):
        _save(source, run_id=run_id)
    assert not (state_home / "minicode" / "memory").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_memory_directory_and_file_are_private(source) -> None:
    _save(source)
    path = _record_path(source)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
@pytest.mark.parametrize("shared", ["directory", "file"])
def test_shared_memory_path_is_rejected_not_chmodded(source, shared: str) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    selected = path.parent if shared == "directory" else path
    mode = 0o755 if shared == "directory" else 0o644
    selected.chmod(mode)
    with pytest.raises(PermissionError, match="group-accessible"):
        load_saved_test_target(workspace=workspace, state_home=state_home)
    assert stat.S_IMODE(selected.stat().st_mode) == mode


@pytest.mark.parametrize("symlink", ["directory", "file"])
def test_memory_directory_or_file_symlink_is_rejected(source, symlink: str) -> None:
    workspace, state_home, _ = source
    _save(source)
    path = _record_path(source)
    selected = path.parent if symlink == "directory" else path
    moved = selected.with_name(selected.name + ".moved")
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=symlink == "directory")
    with pytest.raises(PermissionError, match="symlink"):
        load_saved_test_target(workspace=workspace, state_home=state_home)


def test_failed_publication_leaves_no_partial_record_or_temp(
    source, monkeypatch
) -> None:
    _, state_home, _ = source

    def fail_link(*args, **kwargs):
        raise OSError("simulated publication failure")

    monkeypatch.setattr(memory_store.os, "link", fail_link)
    with pytest.raises(OSError, match="publication failure"):
        _save(source)
    root = state_home / "minicode" / "memory"
    assert not tuple(root.rglob("test_target.json"))
    assert not tuple(root.rglob("*.tmp"))


def test_failed_flush_leaves_no_formal_record_or_temp(source, monkeypatch) -> None:
    _, state_home, _ = source

    def fail_fsync(*args, **kwargs):
        raise OSError("simulated file synchronization failure")

    monkeypatch.setattr(memory_store.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="synchronization failure"):
        _save(source)
    root = state_home / "minicode" / "memory"
    assert not tuple(root.rglob("test_target.json"))
    assert not tuple(root.rglob("*.tmp"))


def test_atomic_publication_refuses_a_concurrent_record(source, monkeypatch) -> None:
    original_link = os.link
    competing_bytes = b"competing complete record"

    def competing_link(temporary, destination):
        Path(destination).write_bytes(competing_bytes)
        original_link(temporary, destination)

    monkeypatch.setattr(memory_store.os, "link", competing_link)
    with pytest.raises(FileExistsError):
        _save(source)
    path = _record_path(source)
    assert path.read_bytes() == competing_bytes
    assert not tuple(path.parent.glob("*.tmp"))
