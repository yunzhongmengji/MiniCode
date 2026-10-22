"""Derive a bounded test-target candidate from host-supplied run history."""

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.context_retrieval import get_tool_result
from minicode.core.file_checkpoint_store import (
    FileCheckpointStore,
    workspace_checkpoint_root,
)
from minicode.core.tool_calls import ToolCall
from minicode.tools.run_tests import RunTestsArguments
from minicode.workspace import Workspace


class TestTargetCandidate(BaseModel):
    """A source-linked observation, not user approval or an admitted memory."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["test_target"] = "test_target"
    workspace_root: Path
    target_path: str
    source_run_id: str
    source_call_id: str
    source_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("workspace_root")
    @classmethod
    def require_absolute_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("workspace_root must be absolute")
        return value

    @field_validator("target_path")
    @classmethod
    def require_normalized_target(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value.strip()
            or path.is_absolute()
            or ".." in path.parts
            or value.startswith("-")
            or path.as_posix() != value
        ):
            raise ValueError("target_path must be a normalized relative test path")
        return value

    @field_validator("source_run_id", "source_call_id")
    @classmethod
    def require_nonblank_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source identifiers must not be blank")
        return value


def build_test_target_candidate(
    *, workspace: Workspace, checkpoint: RunCheckpoint, call_id: str
) -> TestTargetCandidate:
    """Check one completed run's call/result; do not run, save, or approve anything.

    The host must supply this workspace's authentic checkpoint. This function
    checks consistency, not checkpoint authenticity or future test coverage.
    The output hash identifies evidence; it cannot restore the original output.
    """
    if not isinstance(workspace, Workspace):
        raise TypeError("workspace must be a Workspace")
    if not isinstance(checkpoint, RunCheckpoint):
        raise TypeError("checkpoint must be a RunCheckpoint")
    if not checkpoint.is_completed:
        raise ValueError("test-target candidates require a completed checkpoint")

    result = get_tool_result(checkpoint.message_history, call_id)
    # RunCheckpoint already guarantees unique calls and correlated results.
    call = next(
        item
        for item in checkpoint.message_history
        if isinstance(item, ToolCall) and item.call_id == call_id
    )
    if call.name != "run_tests":
        raise ValueError("test-target evidence must come from run_tests")
    if result.is_error:
        raise ValueError("failed test results cannot support a test-target candidate")

    arguments = RunTestsArguments.model_validate(dict(call.arguments))
    if Path(arguments.path).is_absolute():
        raise ValueError("test-target evidence must use a relative path")
    selected = workspace.resolve_path(arguments.path)
    if not (selected.is_file() or selected.is_dir()):
        raise FileNotFoundError("test target is not an existing file or directory")

    return TestTargetCandidate(
        workspace_root=workspace.root,
        target_path=selected.relative_to(workspace.root).as_posix(),
        source_run_id=checkpoint.run_id,
        source_call_id=call.call_id,
        source_result_sha256=sha256(result.output.encode("utf-8")).hexdigest(),
    )


def load_test_target_candidate(
    *, workspace: Workspace, state_home: Path, run_id: str, call_id: str
) -> TestTargetCandidate:
    """Rebuild an unconfirmed candidate from this project's host-owned state.

    The host supplies state_home, never the model or repository contents.
    Directory scoping prevents ordinary cross-project lookup, not forgery by
    a writer with access to host state. Missing state is not created.
    """
    if not isinstance(workspace, Workspace):
        raise TypeError("workspace must be a Workspace")
    root = workspace_checkpoint_root(
        workspace_root=workspace.root, state_home=state_home
    )
    if not root.is_dir():
        raise FileNotFoundError("no checkpoint directory for this workspace")
    checkpoint = FileCheckpointStore(root).latest(run_id)
    if checkpoint is None:
        raise FileNotFoundError("no checkpoint found for this workspace and run")
    return build_test_target_candidate(
        workspace=workspace, checkpoint=checkpoint, call_id=call_id
    )
