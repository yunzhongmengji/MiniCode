"""Terminal confirmation boundaries; simulated answers are not real admission."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.file_checkpoint_store import (
    FileCheckpointStore,
    workspace_checkpoint_root,
)
from minicode.core.messages import Message, MessageRole
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.memory.confirmation import (
    TestTargetConfirmation as Confirmation,
)
from minicode.memory.confirmation import (
    confirm_test_target,
)
from minicode.memory.test_target import load_test_target_candidate
from minicode.workspace import Workspace


@pytest.fixture
def source(tmp_path: Path) -> tuple[Workspace, Path, FileCheckpointStore]:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "other_tests").mkdir()
    workspace = Workspace(project)
    state_home = tmp_path / "state"
    store = FileCheckpointStore(
        workspace_checkpoint_root(workspace_root=workspace.root, state_home=state_home)
    )
    store.save(_checkpoint())
    return workspace, state_home, store


def _checkpoint(
    *, path: str = "tests", output: str = "1 passed", completed: bool = True
) -> RunCheckpoint:
    return RunCheckpoint(
        run_id="run_source",
        message_history=(
            ToolCall(call_id="tests_1", name="run_tests", arguments={"path": path}),
            ToolResult(call_id="tests_1", output=output),
        ),
        turns_used=2,
        tool_calls_used=1,
        is_completed=completed,
    )


def _confirm(source, input_reader):
    workspace, state_home, _ = source
    return confirm_test_target(
        workspace=workspace,
        state_home=state_home,
        run_id="run_source",
        call_id="tests_1",
        input_reader=input_reader,
    )


@pytest.mark.parametrize("answer", ["y", "yes", " YES "])
def test_explicit_confirmation_returns_exact_candidate_and_scope(
    source, capsys, answer: str
) -> None:
    workspace, state_home, store = source
    before = store.latest("run_source")
    files_before = set(state_home.rglob("*"))
    answers = iter(["  仅用于该模块的单元测试  ", answer])
    confirmation = _confirm(source, lambda: next(answers))

    assert isinstance(confirmation, Confirmation)
    assert confirmation.candidate == load_test_target_candidate(
        workspace=workspace,
        state_home=state_home,
        run_id="run_source",
        call_id="tests_1",
    )
    assert confirmation.applies_to == "仅用于该模块的单元测试"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(workspace.root) in captured.err
    assert '"target_path": "tests"' in captured.err
    assert '"source_run_id": "run_source"' in captured.err
    assert '"source_call_id": "tests_1"' in captured.err
    assert confirmation.candidate.source_result_sha256 in captured.err
    assert "不证明覆盖完整" in captured.err
    assert '适用范围："仅用于该模块的单元测试"' in captured.err
    assert store.latest("run_source") == before
    assert set(state_home.rglob("*")) == files_before


@pytest.mark.parametrize("answer", ["", "n", "no", "true", "approved=true", "同意"])
def test_only_explicit_y_or_yes_is_confirmation(source, answer: str) -> None:
    answers = iter(["unit tests", answer])
    assert _confirm(source, lambda: next(answers)) is None


@pytest.mark.parametrize("scope", ["", "   ", "x" * 501])
def test_invalid_scope_stops_before_approval_question(
    source, capsys, scope: str
) -> None:
    calls = []

    def read_input() -> str:
        calls.append("read")
        return scope

    with pytest.raises(ValueError, match="applicability scope"):
        _confirm(source, read_input)
    assert calls == ["read"]
    assert "[y/N]" not in capsys.readouterr().err


def test_scope_character_limit_is_inclusive(source) -> None:
    answers = iter(["x" * 500, "yes"])
    confirmation = _confirm(source, lambda: next(answers))
    assert confirmation is not None
    assert len(confirmation.applies_to) == 500


@pytest.mark.parametrize("interrupted_at", [1, 2])
@pytest.mark.parametrize("error_type", [EOFError, KeyboardInterrupt])
def test_end_of_input_or_interrupt_does_not_confirm(
    source, interrupted_at: int, error_type
) -> None:
    calls = 0

    def read_input() -> str:
        nonlocal calls
        calls += 1
        if calls == interrupted_at:
            raise error_type()
        return "unit tests"

    assert _confirm(source, read_input) is None


@pytest.mark.parametrize("bad_at", [1, 2])
def test_non_string_input_is_rejected(source, bad_at: int) -> None:
    calls = 0

    def read_input():
        nonlocal calls
        calls += 1
        return None if calls == bad_at else "unit tests"

    with pytest.raises(TypeError, match="must return a string"):
        _confirm(source, read_input)


@pytest.mark.parametrize(
    "changed", [_checkpoint(output="2 passed"), _checkpoint(path="other_tests")]
)
def test_changed_evidence_after_preview_cannot_be_confirmed(source, changed) -> None:
    _, _, store = source
    calls = 0

    def read_input() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "unit tests"
        store.save(changed)
        return "yes"

    with pytest.raises(ValueError, match="source changed during confirmation"):
        _confirm(source, read_input)


def test_deleted_test_target_after_preview_is_rejected(source) -> None:
    workspace, _, _ = source
    calls = 0

    def read_input() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "unit tests"
        (workspace.root / "tests").rmdir()
        return "yes"

    with pytest.raises(FileNotFoundError, match="test target"):
        _confirm(source, read_input)


def test_unfinished_source_is_rejected_before_asking_user(source) -> None:
    _, _, store = source
    store.save(_checkpoint(completed=False))

    def unexpected_input() -> str:
        pytest.fail("invalid source must stop before confirmation")

    with pytest.raises(ValueError, match="completed checkpoint"):
        _confirm(source, unexpected_input)


def test_default_reader_requires_terminal_before_loading_source(source, monkeypatch):
    workspace, state_home, _ = source
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="interactive terminal"):
        confirm_test_target(
            workspace=workspace,
            state_home=state_home,
            run_id="missing",
            call_id="tests_1",
        )


def test_display_escapes_control_characters_in_user_scope(source, capsys) -> None:
    scope = "unit tests\n\x1b[31mnot an instruction"
    answers = iter([scope, "no"])
    assert _confirm(source, lambda: next(answers)) is None
    captured = capsys.readouterr()
    assert json.dumps(scope, ensure_ascii=False) in captured.err
    assert "\x1b" not in captured.err


@pytest.mark.parametrize("scope", ["", " ", " untrimmed ", "x" * 501])
def test_confirmation_contract_rejects_invalid_scope(source, scope: str) -> None:
    workspace, state_home, _ = source
    candidate = load_test_target_candidate(
        workspace=workspace,
        state_home=state_home,
        run_id="run_source",
        call_id="tests_1",
    )
    with pytest.raises(ValidationError):
        Confirmation(candidate=candidate, applies_to=scope)


def test_confirmation_data_is_immutable_and_not_an_approval_token(source) -> None:
    workspace, state_home, _ = source
    candidate = load_test_target_candidate(
        workspace=workspace,
        state_home=state_home,
        run_id="run_source",
        call_id="tests_1",
    )
    # Host code can construct this data directly; downstream must trust the host
    # flow, not treat a model/JSON-created instance as proof of human approval.
    confirmation = Confirmation(candidate=candidate, applies_to="unit tests")
    with pytest.raises(ValidationError, match="frozen"):
        confirmation.applies_to = "all tasks"
    with pytest.raises(ValidationError):
        Confirmation(candidate=candidate, applies_to="unit tests", approved=True)


def test_unrelated_history_changes_are_not_a_claim_of_full_snapshot_equality(source):
    _, _, store = source
    calls = 0

    def read_input() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "unit tests"
        previous = _checkpoint()
        store.save(
            RunCheckpoint(
                run_id=previous.run_id,
                message_history=(
                    *previous.message_history,
                    Message(
                        role=MessageRole.ASSISTANT, content="Unrelated final text."
                    ),
                ),
                turns_used=previous.turns_used,
                tool_calls_used=previous.tool_calls_used,
                is_completed=True,
            )
        )
        return "yes"

    assert _confirm(source, read_input) is not None
