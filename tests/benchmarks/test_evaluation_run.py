import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from minicode import cli
from minicode.core.events import EventKind
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.evaluation_prepare import prepare_evaluation_workspace
from minicode.evaluation_result import parse_trace
from minicode.evaluation_run import EvaluationArm, context_threshold_for_arm, main
from minicode.models.scripted import ScriptedModel


def test_evaluation_run_uses_case_task_and_budget(
    monkeypatch,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )
    received_calls: list[tuple[tuple[str, ...], int | None, object, object, int]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
        model_max_retries: int,
    ) -> int:
        assert arguments is not None
        received_calls.append(
            (
                tuple(arguments),
                max_inline_tool_result_bytes,
                budgeted_context_configuration,
                expected_model,
                model_max_retries,
            ),
        )
        return 17

    monkeypatch.setattr(
        cli,
        "main",
        record_cli_call,
    )

    exit_code = main(
        [
            "--case-root",
            str(case_root),
        ]
    )

    assert exit_code == 17
    assert received_calls == [
        (
            (
                "run",
                (case_root / "task.txt").read_text(encoding="utf-8").strip(),
                "--max-turns",
                "8",
                "--max-tool-calls",
                "8",
                "--trace",
            ),
            None,
            None,
            None,
            0,
        )
    ]


def test_evaluation_run_passes_projection_arm_to_python_cli(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks" / "coding_agent" / "cases" / "single_file_batching"
    )
    received_thresholds: list[int | None] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
        model_max_retries: int,
    ) -> int:
        assert arguments is not None
        assert budgeted_context_configuration is None
        assert expected_model is None
        assert model_max_retries == 0
        received_thresholds.append(max_inline_tool_result_bytes)
        return 0

    monkeypatch.setattr(cli, "main", record_cli_call)

    assert main(["--case-root", str(case_root), "--arm", "projection"]) == 0
    assert received_thresholds == [500]


@pytest.mark.parametrize("arm", (EvaluationArm.BASELINE, EvaluationArm.PROJECTION))
def test_evaluation_run_resolves_registered_v4_arm_from_protocol(
    monkeypatch,
    arm: EvaluationArm,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root
        / "benchmarks"
        / "coding_agent"
        / "cases"
        / "large_search_context_recall"
    )
    protocol_path = (
        project_root
        / "benchmarks"
        / "context_projection"
        / "real_model_protocol_v4.json"
    )
    received: list[tuple[int | None, object, object]] = []

    def record_cli_call(
        arguments: Sequence[str] | None,
        *,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
        model_max_retries: int,
    ) -> int:
        assert arguments is not None
        received.append(
            (
                max_inline_tool_result_bytes,
                budgeted_context_configuration,
                expected_model,
            )
        )
        assert model_max_retries == 0
        return 0

    monkeypatch.setattr(cli, "main", record_cli_call)

    assert (
        main(
            [
                "--case-root",
                str(case_root),
                "--context-protocol",
                str(protocol_path),
                "--arm",
                arm,
            ]
        )
        == 0
    )
    assert received[0][0] is None
    assert received[0][2] == "qwen3.7-flash-2026-07-15"

    if arm is EvaluationArm.BASELINE:
        assert received[0][1] is None
    else:
        configuration = received[0][1]
        assert configuration.max_request_bytes == 10_000
        assert configuration.protected_recent_batch_count == 2


def test_evaluation_run_requires_explicit_arm_with_registered_protocol() -> None:
    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root
        / "benchmarks"
        / "coding_agent"
        / "cases"
        / "large_search_context_recall"
    )
    protocol_path = (
        project_root
        / "benchmarks"
        / "context_projection"
        / "real_model_protocol_v4.json"
    )

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--case-root",
                str(case_root),
                "--context-protocol",
                str(protocol_path),
            ]
        )

    assert exc_info.value.code == 2


def test_context_threshold_for_arm_keeps_baseline_disabled() -> None:
    assert context_threshold_for_arm(EvaluationArm.BASELINE) is None
    assert context_threshold_for_arm(EvaluationArm.PROJECTION) == 500


def test_evaluation_run_rejects_unknown_arm_before_cli(monkeypatch) -> None:
    def unexpected_cli_call(*args, **kwargs):
        pytest.fail("invalid arm must be rejected before the coding CLI")

    monkeypatch.setattr(cli, "main", unexpected_cli_call)

    with pytest.raises(SystemExit) as exc_info:
        main(["--case-root", ".", "--arm", "unknown"])

    assert exc_info.value.code == 2


@pytest.mark.parametrize("enable_skills", (False, True), ids=("default", "skills"))
def test_evaluation_run_delivers_optional_skill_instructions_to_model(
    monkeypatch,
    tmp_path: Path,
    capsys,
    enable_skills: bool,
) -> None:
    class OfflineClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    project_root = Path(__file__).resolve().parents[2]
    case_root = (
        project_root / "benchmarks/coding_agent/cases/multi_file_inventory_contract"
    )
    skills_root = tmp_path / "trusted skills"
    shutil.copytree(
        project_root / "benchmarks/skill_task_comparison/v1/skills",
        skills_root,
    )
    workspace = prepare_evaluation_workspace(case_root, temporary_root=tmp_path)
    model = ScriptedModel(responses=(ModelResponse(content="Offline wiring checked."),))
    client = OfflineClient()
    retry_limits: list[int] = []

    def build_client(config, *, max_retries: int) -> OfflineClient:
        retry_limits.append(max_retries)
        return client

    monkeypatch.chdir(workspace)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-test-key")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "build_dashscope_client", build_client)
    monkeypatch.setattr(cli, "build_dashscope_model", lambda config, *, client: model)
    arguments = ["--case-root", str(case_root)]
    if enable_skills:
        arguments += ["--skills-root", "../trusted skills"]

    assert main(arguments) == 0

    captured = capsys.readouterr()
    assert client.closed is True
    assert retry_limits == [0]
    assert captured.out == "Offline wiring checked.\n"
    assert len(model.requests) == 1
    request = model.requests[0]
    assert request.conversation == (
        Message(
            role=MessageRole.USER,
            content=(case_root / "task.txt").read_text(encoding="utf-8").strip(),
        ),
    )
    assert len(request.instructions) == (2 if enable_skills else 1)
    if enable_skills:
        body = (
            (skills_root / "inventory-contract-review/SKILL.md")
            .read_text(encoding="utf-8")
            .strip()
        )
        assert request.instructions[1] == (
            "# Loaded Skills\n\n## Skill: inventory-contract-review\n\n" + body
        )
    replay = parse_trace(captured.err)
    skill_events = tuple(
        event.kind for event in replay.events if event.kind.value.startswith("skill_")
    )
    assert skill_events == (
        (
            EventKind.SKILL_SELECTION_FINISHED,
            EventKind.SKILL_LOAD_STARTED,
            EventKind.SKILL_LOAD_FINISHED,
        )
        if enable_skills
        else ()
    )
    assert replay.events[0].payload["max_turns"] == 8
    assert replay.events[0].payload["max_tool_calls"] == 8


def test_evaluation_run_rejects_skill_directory_with_registered_context_protocol(
    monkeypatch,
    capsys,
) -> None:
    def unexpected_cli_call(*args, **kwargs):
        pytest.fail("mixed experiment configuration must be rejected before CLI")

    monkeypatch.setattr(cli, "main", unexpected_cli_call)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--case-root",
                ".",
                "--skills-root",
                "trusted-skills",
                "--context-protocol",
                "registered-context.json",
                "--arm",
                "baseline",
            ]
        )

    assert exc_info.value.code == 2
    assert "--skills-root cannot be combined with --context-protocol" in (
        capsys.readouterr().err
    )
