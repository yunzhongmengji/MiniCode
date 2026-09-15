from pathlib import Path

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
