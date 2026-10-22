import json
import os
import stat
from pathlib import Path

import pytest

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.file_checkpoint_store import FileCheckpointStore
from minicode.core.messages import Message, MessageRole


def test_file_checkpoint_store_recovers_latest_across_instances(
    tmp_path: Path,
) -> None:
    first = RunCheckpoint(
        run_id="run/001",
        message_history=(),
        turns_used=1,
        tool_calls_used=0,
    )
    latest = RunCheckpoint(
        run_id="run/001",
        message_history=(
            Message(
                role=MessageRole.USER,
                content="Continue the interrupted task.",
            ),
        ),
        turns_used=2,
        tool_calls_used=0,
        is_completed=True,
    )
    writer = FileCheckpointStore(tmp_path)

    writer.save(first)
    writer.save(latest)

    reader = FileCheckpointStore(tmp_path)

    assert reader.latest("run/001") == latest
    assert reader.latest("missing_run") is None
    assert len(tuple(tmp_path.glob("*.json"))) == 1
    assert not tuple(tmp_path.glob("*.tmp"))


def test_file_checkpoint_store_recovers_skill_instructions(tmp_path: Path) -> None:
    checkpoint = RunCheckpoint(
        run_id="run_skill",
        message_history=(),
        turns_used=1,
        tool_calls_used=0,
        skill_instructions="Check the README before answering.",
    )
    FileCheckpointStore(tmp_path).save(checkpoint)

    stored_file = next(tmp_path.glob("*.json"))
    document = json.loads(stored_file.read_text(encoding="utf-8"))

    assert document["schema_version"] == 3
    assert document["skill_instructions"] == checkpoint.skill_instructions
    assert FileCheckpointStore(tmp_path).latest("run_skill") == checkpoint


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits only")
def test_file_checkpoint_store_keeps_skill_snapshot_private(tmp_path: Path) -> None:
    root = tmp_path / "private-state"
    checkpoint = RunCheckpoint(
        run_id="run_skill",
        message_history=(),
        turns_used=1,
        tool_calls_used=0,
        skill_instructions="Private Skill instructions.",
    )

    FileCheckpointStore(root).save(checkpoint)

    stored_file = next(root.glob("*.json"))
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_file.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits only")
def test_file_checkpoint_store_rejects_existing_shared_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shared-state"
    root.mkdir(mode=0o700)
    root.chmod(0o755)

    with pytest.raises(PermissionError, match="must not be group-accessible"):
        FileCheckpointStore(root)

    assert stat.S_IMODE(root.stat().st_mode) == 0o755
