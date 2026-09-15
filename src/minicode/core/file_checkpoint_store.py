"""File-backed storage for durable query-loop checkpoints."""

import hashlib
import os
import tempfile
from pathlib import Path

from minicode.core.checkpoint_codec import (
    checkpoint_from_json,
    checkpoint_to_json,
)
from minicode.core.checkpoints import RunCheckpoint


class FileCheckpointStore:
    """Keep the latest checkpoint for each run in a JSON file."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)
        self._root.mkdir(
            mode=0o700,
            parents=True,
            exist_ok=True,
        )

    def save(self, checkpoint: RunCheckpoint) -> None:
        """Atomically replace the latest checkpoint for one run."""
        if not isinstance(checkpoint, RunCheckpoint):
            raise TypeError("checkpoint must be a RunCheckpoint")

        destination = self._path_for(checkpoint.run_id)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=self._root,
        )
        temporary_path = Path(temporary_name)

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as temporary_file:
                temporary_file.write(checkpoint_to_json(checkpoint))
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def latest(self, run_id: str) -> RunCheckpoint | None:
        """Load the latest checkpoint for one run when it exists."""
        path = self._path_for(run_id)

        if not path.exists():
            return None

        checkpoint = checkpoint_from_json(path.read_text(encoding="utf-8"))

        if checkpoint.run_id != run_id:
            raise ValueError("checkpoint run_id does not match its storage key")

        return checkpoint

    def _path_for(self, run_id: str) -> Path:
        if not isinstance(run_id, str):
            raise TypeError("run_id must be a string")

        if not run_id.strip():
            raise ValueError("run_id must not be blank")

        storage_key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self._root / f"{storage_key}.json"
