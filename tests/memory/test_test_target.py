"""Test candidate contracts without memory storage or model requests."""

from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.messages import Message, MessageRole
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.memory.test_target import TestTargetCandidate as Candidate
from minicode.memory.test_target import build_test_target_candidate
from minicode.tools.process import AsyncioProcessRunner
from minicode.tools.run_tests import RunTestsArguments, RunTestsTool
from minicode.workspace import Workspace, WorkspacePathError


def _checkpoint(
    *,
    arguments: dict[str, object] | None = None,
    name: str = "run_tests",
    output: str = "1 passed",
    is_error: bool = False,
    completed: bool = True,
) -> RunCheckpoint:
    return RunCheckpoint(
        run_id="run_test_source",
        message_history=(
            Message(role=MessageRole.USER, content="Check unit tests."),
            ToolCall(
                call_id="tests_1",
                name=name,
                arguments={"path": "tests/unit"} if arguments is None else arguments,
            ),
            ToolResult(call_id="tests_1", output=output, is_error=is_error),
        ),
        turns_used=2,
        tool_calls_used=1,
        is_completed=completed,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_one.py").write_text("pass\n")
    return Workspace(tmp_path)


def test_candidate_derives_fact_and_source_without_copying_output(workspace) -> None:
    checkpoint = _checkpoint(output="1 passed\n内部日志不应复制到候选")
    history = checkpoint.message_history

    candidate = build_test_target_candidate(
        workspace=workspace, checkpoint=checkpoint, call_id="tests_1"
    )

    assert candidate.kind == "test_target"
    assert candidate.workspace_root == workspace.root
    assert candidate.target_path == "tests/unit"
    assert candidate.source_run_id == checkpoint.run_id
    assert candidate.source_call_id == "tests_1"
    assert (
        candidate.source_result_sha256
        == sha256("1 passed\n内部日志不应复制到候选".encode()).hexdigest()
    )
    assert set(Candidate.model_fields) == {
        "kind",
        "workspace_root",
        "target_path",
        "source_run_id",
        "source_call_id",
        "source_result_sha256",
    }
    assert checkpoint.message_history is history


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({}, "tests"),
        ({"path": "./tests/unit"}, "tests/unit"),
        ({"path": "tests/../tests/unit"}, "tests/unit"),
        ({"path": "tests/unit/test_one.py"}, "tests/unit/test_one.py"),
        ({"path": "."}, "."),
    ],
)
def test_candidate_uses_real_tool_defaults_and_normalizes_target(
    workspace, arguments, expected
) -> None:
    candidate = build_test_target_candidate(
        workspace=workspace,
        checkpoint=_checkpoint(arguments=arguments),
        call_id="tests_1",
    )
    assert candidate.target_path == expected


def test_candidate_selects_requested_call_not_another_success(workspace) -> None:
    checkpoint = RunCheckpoint(
        run_id="run_two_tests",
        message_history=(
            ToolCall(call_id="first", name="run_tests", arguments={"path": "tests"}),
            ToolResult(call_id="first", output="first output"),
            ToolCall(
                call_id="second", name="run_tests", arguments={"path": "tests/unit"}
            ),
            ToolResult(call_id="second", output="second output"),
        ),
        turns_used=3,
        tool_calls_used=2,
        is_completed=True,
    )
    candidate = build_test_target_candidate(
        workspace=workspace, checkpoint=checkpoint, call_id="second"
    )
    assert candidate.target_path == "tests/unit"
    assert candidate.source_call_id == "second"
    assert candidate.source_result_sha256 == sha256(b"second output").hexdigest()


@pytest.mark.parametrize("call_id", ["missing", "", "  ", None, 123])
def test_candidate_rejects_missing_or_invalid_call_id(workspace, call_id) -> None:
    with pytest.raises((LookupError, TypeError, ValueError)):
        build_test_target_candidate(
            workspace=workspace, checkpoint=_checkpoint(), call_id=call_id
        )


@pytest.mark.parametrize("name", ["read_file", "search_text", "edit_file"])
def test_success_from_non_test_tool_is_not_test_evidence(workspace, name) -> None:
    with pytest.raises(ValueError, match="must come from run_tests"):
        build_test_target_candidate(
            workspace=workspace, checkpoint=_checkpoint(name=name), call_id="tests_1"
        )


def test_failed_result_cannot_be_rescued_by_passed_text(workspace) -> None:
    with pytest.raises(ValueError, match="failed test results"):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(output="1 passed, 1 failed", is_error=True),
            call_id="tests_1",
        )


@pytest.mark.parametrize("output", ["", "3 skipped", "arbitrary log text"])
def test_candidate_does_not_claim_coverage_from_output_words(workspace, output) -> None:
    # With authentic RunTestsTool evidence, is_error reflects process failure.
    # We do not reinterpret pytest prose or claim that tests were all exercised.
    candidate = build_test_target_candidate(
        workspace=workspace,
        checkpoint=_checkpoint(output=output),
        call_id="tests_1",
    )
    assert candidate.source_result_sha256 == sha256(output.encode()).hexdigest()


def test_unfinished_run_does_not_produce_candidate(workspace) -> None:
    with pytest.raises(ValueError, match="completed checkpoint"):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(completed=False),
            call_id="tests_1",
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": ""},
        {"path": "  "},
        {"path": "-q"},
        {"path": 42},
        {"path": "tests", "command": "echo 1 passed"},
    ],
)
def test_candidate_reuses_tool_argument_validation(workspace, arguments) -> None:
    with pytest.raises(ValidationError):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(arguments=arguments),
            call_id="tests_1",
        )


def test_candidate_rejects_absolute_path_even_inside_workspace(workspace) -> None:
    with pytest.raises(ValueError, match="relative path"):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(arguments={"path": str(workspace.root / "tests")}),
            call_id="tests_1",
        )


def test_candidate_rejects_parent_escape(workspace) -> None:
    with pytest.raises(WorkspacePathError):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(arguments={"path": "../outside"}),
            call_id="tests_1",
        )


def test_candidate_rejects_external_symlink(workspace, tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    (root / "tests").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspacePathError):
        build_test_target_candidate(
            workspace=Workspace(root),
            checkpoint=_checkpoint(arguments={}),
            call_id="tests_1",
        )


def test_candidate_normalizes_internal_symlink(workspace) -> None:
    (workspace.root / "alias").symlink_to("tests/unit", target_is_directory=True)
    candidate = build_test_target_candidate(
        workspace=workspace,
        checkpoint=_checkpoint(arguments={"path": "alias"}),
        call_id="tests_1",
    )
    assert candidate.target_path == "tests/unit"


def test_candidate_rejects_missing_target(workspace) -> None:
    with pytest.raises(FileNotFoundError):
        build_test_target_candidate(
            workspace=workspace,
            checkpoint=_checkpoint(arguments={"path": "tests/absent"}),
            call_id="tests_1",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "shell_command"),
        ("workspace_root", Path("relative")),
        ("target_path", "/outside"),
        ("target_path", "../outside"),
        ("target_path", "./tests"),
        ("target_path", "-q"),
        ("target_path", ""),
        ("source_run_id", "  "),
        ("source_call_id", ""),
        ("source_result_sha256", "not-a-sha256"),
        ("approved", True),
    ],
)
def test_candidate_contract_rejects_invalid_or_approval_fields(workspace, field, value):
    fields = {
        "workspace_root": workspace.root,
        "target_path": "tests/unit",
        "source_run_id": "run_source",
        "source_call_id": "tests_1",
        "source_result_sha256": sha256(b"1 passed").hexdigest(),
    }
    fields[field] = value
    with pytest.raises(ValidationError):
        Candidate(**fields)


def test_candidate_is_immutable(workspace) -> None:
    candidate = build_test_target_candidate(
        workspace=workspace, checkpoint=_checkpoint(), call_id="tests_1"
    )
    with pytest.raises(ValidationError, match="frozen"):
        candidate.target_path = "tests/other"


def test_mismatched_result_is_rejected_by_checkpoint_before_candidate(workspace):
    with pytest.raises(ValueError, match="preceding tool call"):
        RunCheckpoint(
            run_id="run_bad_pair",
            message_history=(
                ToolCall(call_id="tests_1", name="run_tests", arguments={}),
                ToolResult(call_id="other_call", output="1 passed"),
            ),
            turns_used=1,
            tool_calls_used=1,
            is_completed=True,
        )


@pytest.mark.asyncio
async def test_real_pytest_result_can_support_candidate(workspace) -> None:
    (workspace.root / "tests/unit/test_one.py").write_text(
        "def test_one():\n    assert 1 + 1 == 2\n"
    )
    tool = RunTestsTool(workspace, runner=AsyncioProcessRunner())
    output = await tool.execute(RunTestsArguments(path="tests/unit"))
    assert "1 passed" in output

    candidate = build_test_target_candidate(
        workspace=workspace,
        checkpoint=_checkpoint(output=output),
        call_id="tests_1",
    )

    assert candidate.target_path == "tests/unit"
    assert candidate.source_result_sha256 == sha256(output.encode()).hexdigest()
    assert not (workspace.root / "memory.json").exists()


def test_forged_candidate_does_not_imply_authenticated_evidence(workspace) -> None:
    # This module checks a supplied snapshot, not its origin or workspace binding.
    # A memory-admission step must not trust a hand-constructed record as approval.
    candidate = Candidate(
        workspace_root=workspace.root,
        target_path="tests/unit",
        source_run_id="invented_run",
        source_call_id="invented_call",
        source_result_sha256=sha256(b"invented output").hexdigest(),
    )
    assert candidate.source_run_id == "invented_run"
