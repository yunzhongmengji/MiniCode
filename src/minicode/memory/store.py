"""One host-confirmed test target per project; no model integration."""

import os
import stat
import tempfile
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from minicode.memory.confirmation import TestTargetConfirmation, confirm_test_target
from minicode.memory.test_target import load_test_target_candidate
from minicode.workspace import Workspace

MAX_MEMORY_RECORD_BYTES = 16_384


class _StoredTestTarget(BaseModel):
    """Versioned disk format, not proof of human approval."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: int = Field(ge=1, le=1)
    confirmation: TestTargetConfirmation


def _memory_path(*, workspace: Workspace, state_home: Path) -> Path:
    if not isinstance(workspace, Workspace):
        raise TypeError("workspace must be a Workspace")
    if not state_home.is_absolute():
        raise ValueError("state_home must be absolute")
    key = sha256(str(workspace.root).encode("utf-8")).hexdigest()
    return state_home / "minicode" / "memory" / key / "test_target.json"


def _require_private_path(path: Path, *, directory: bool) -> None:
    """Check the project directory/file, not every ancestor or concurrent access."""
    if path.is_symlink():
        raise PermissionError("memory project directory/file must not be a symlink")
    mode = path.stat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError("memory path must be a directory or regular record file")
    if os.name == "posix" and stat.S_IMODE(mode) & 0o077:
        raise PermissionError("memory directory/file must not be group-accessible")


def _recheck_source(
    confirmation: TestTargetConfirmation, *, workspace: Workspace, state_home: Path
) -> None:
    candidate = confirmation.candidate
    if candidate.workspace_root != workspace.root:
        raise ValueError("saved test target belongs to another workspace")
    current = load_test_target_candidate(
        workspace=workspace,
        state_home=state_home,
        run_id=candidate.source_run_id,
        call_id=candidate.source_call_id,
    )
    if current != candidate:
        raise ValueError("saved test-target source changed; review again")


def confirm_and_save_test_target(
    *,
    workspace: Workspace,
    state_home: Path,
    run_id: str,
    call_id: str,
    input_reader: Callable[[], str] = input,
) -> TestTargetConfirmation | None:
    """Host-only admission: ask the user and atomically create one private record.

    No supplied confirmation/approved flag is accepted. Input-reader injection
    is for trusted host tests. Existing records are never silently replaced.
    Source comparison is not a lock, signature, or project-file version check.
    """
    path = _memory_path(workspace=workspace, state_home=state_home)
    if path.parent.exists() or path.parent.is_symlink():
        _require_private_path(path.parent, directory=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "test target already saved; replacement is not supported yet"
        )
    confirmation = confirm_test_target(
        workspace=workspace,
        state_home=state_home,
        run_id=run_id,
        call_id=call_id,
        input_reader=input_reader,
    )
    if confirmation is None:
        return None
    encoded = (
        _StoredTestTarget(schema_version=1, confirmation=confirmation).model_dump_json(
            indent=2
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_MEMORY_RECORD_BYTES:
        raise ValueError("memory record exceeds the 16384-byte limit")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_private_path(path.parent, directory=True)
    descriptor, name = tempfile.mkstemp(
        prefix=".test_target.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        _recheck_source(confirmation, workspace=workspace, state_home=state_home)
        # Atomic first publication; unlike replace(), link() refuses an existing
        # destination even if another writer created it after the initial check.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return confirmation


def load_saved_test_target(
    *, workspace: Workspace, state_home: Path
) -> TestTargetConfirmation | None:
    """Read one host record and recheck its source; never create missing state.

    Missing records return None. Invalid/unverifiable records raise instead of
    becoming usable references. Host-state writers can still forge disk data.
    """
    path = _memory_path(workspace=workspace, state_home=state_home)
    if not path.parent.exists() and not path.parent.is_symlink():
        return None
    _require_private_path(path.parent, directory=True)
    if not path.exists() and not path.is_symlink():
        return None
    _require_private_path(path, directory=False)
    with path.open("rb") as source:
        encoded = source.read(MAX_MEMORY_RECORD_BYTES + 1)
    if len(encoded) > MAX_MEMORY_RECORD_BYTES:
        raise ValueError("memory record exceeds the 16384-byte limit")
    record = _StoredTestTarget.model_validate_json(encoded)
    _recheck_source(record.confirmation, workspace=workspace, state_home=state_home)
    return record.confirmation
