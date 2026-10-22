"""Check the fixed Skill A/B fixture and scripted end-to-end records."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from minicode.cli import _print_trace
from minicode.coding_agent import build_coding_agent
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.evaluation_case import load_case_manifest
from minicode.evaluation_prepare import prepare_evaluation_workspace
from minicode.evaluation_result import main as record_evaluation_main
from minicode.evaluation_result import parse_trace, record_result
from minicode.evaluation_summary import main as summarize_evaluation_main
from minicode.models.scripted import ScriptedModel
from minicode.skills.context import SkillContextBuilder
from minicode.skills.discovery import FileSkillCatalogLoader
from minicode.skills.loader import FileSkillLoader
from minicode.skills.router import KeywordSkillRouter
from minicode.tools.process import AsyncioProcessRunner
from minicode.workspace import Workspace

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CASE_ROOT = (
    _PROJECT_ROOT / "benchmarks/coding_agent/cases/multi_file_inventory_contract"
)
_NEGATIVE_CASE_ROOT = (
    _PROJECT_ROOT / "benchmarks/coding_agent/cases/readonly_pagination_diagnosis"
)
_SKILL_ROOT = _PROJECT_ROOT / "benchmarks/skill_task_comparison/v1/skills"


@pytest.mark.asyncio
async def test_skill_selects_inventory_task_but_not_unrelated_task() -> None:
    skill_workspace = Workspace(_SKILL_ROOT)
    catalog = await FileSkillCatalogLoader(skill_root=skill_workspace).load()
    provider = SkillContextBuilder(
        router=KeywordSkillRouter(catalog=catalog),
        loader=FileSkillLoader(skill_root=skill_workspace),
    )

    task = (_CASE_ROOT / "task.txt").read_text(encoding="utf-8").strip()
    unrelated_task = (
        (_NEGATIVE_CASE_ROOT / "task.txt").read_text(encoding="utf-8").strip()
    )
    selected = await provider.build(task)
    unrelated = await provider.build(unrelated_task)

    assert tuple(skill.manifest.name for skill in selected.skills) == (
        "inventory-contract-review",
    )
    assert "Cross-file data contract review" in selected.render()
    assert unrelated.skills == ()
    assert unrelated.render() == ""


def test_case_acceptance_is_shared_and_independent_of_skill(
    tmp_path: Path,
) -> None:
    baseline = prepare_evaluation_workspace(_CASE_ROOT, temporary_root=tmp_path)
    treatment = prepare_evaluation_workspace(_CASE_ROOT, temporary_root=tmp_path)
    assert baseline != treatment
    assert not tuple(baseline.rglob("manifest.json"))
    assert not tuple(treatment.rglob("SKILL.md"))
    for filename in ("inventory.py", "report.py"):
        assert (baseline / filename).read_bytes() == (treatment / filename).read_bytes()

    acceptance = _CASE_ROOT / "acceptance.py"

    def check(workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, str(acceptance), str(workspace)),
            check=False,
            capture_output=True,
            text=True,
        )

    assert check(baseline).returncode != 0
    assert check(treatment).returncode != 0

    for filename in ("inventory.py", "report.py"):
        path = treatment / filename
        original = path.read_text(encoding="utf-8")
        assert "quantity" in original
        path.write_text(original.replace("quantity", "stock"), encoding="utf-8")

    result = check(treatment)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS multi_file_inventory_contract"
    assert check(baseline).returncode != 0


def _inventory_responses(*, complete_fix: bool) -> tuple[ModelResponse, ...]:
    """Prescribe the same actions for both arms, optionally leaving a bug."""
    edits = (
        ToolCall(
            call_id="edit_inventory",
            name="edit_file",
            arguments={
                "path": "inventory.py",
                "old_text": '"quantity": stock',
                "new_text": '"stock": stock',
            },
        ),
    )
    if complete_fix:
        edits += (
            ToolCall(
                call_id="edit_report",
                name="edit_file",
                arguments={
                    "path": "report.py",
                    "old_text": "record['quantity']",
                    "new_text": "record['stock']",
                },
            ),
        )

    return (
        ModelResponse(
            content="",
            tool_calls=tuple(
                ToolCall(
                    call_id=f"read_{index}",
                    name="read_file",
                    arguments={"path": path},
                )
                for index, path in enumerate(
                    ("inventory.py", "report.py", "tests/test_inventory_contract.py")
                )
            ),
        ),
        ModelResponse(content="", tool_calls=edits),
        ModelResponse(
            content="",
            tool_calls=(ToolCall(call_id="diff", name="git_diff", arguments={}),),
        ),
        ModelResponse(
            content="",
            tool_calls=(
                ToolCall(
                    call_id="tests",
                    name="run_tests",
                    arguments={"path": "tests/test_inventory_contract.py"},
                ),
            ),
        ),
        ModelResponse(content="脚本流程结束，最终结果由独立验收判断。"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "complete_fix",
    (True, False),
    ids=("complete-fix", "missing-consumer-fix"),
)
async def test_scripted_skill_arms_run_tools_and_record_verdicts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    complete_fix: bool,
) -> None:
    class FixtureApprover:
        def __init__(self) -> None:
            self.calls: list[ToolCall] = []

        async def request_approval(self, call: ToolCall, *, reason: str) -> bool:
            self.calls.append(call)
            return (
                call.name == "edit_file"
                and call.arguments.get("path") in ("inventory.py", "report.py")
            ) or (
                call.name == "run_tests"
                and call.arguments.get("path") == "tests/test_inventory_contract.py"
            )

    task = (_CASE_ROOT / "task.txt").read_text(encoding="utf-8").strip()
    manifest = load_case_manifest(_CASE_ROOT)
    responses = _inventory_responses(complete_fix=complete_fix)
    expected_calls = tuple(
        call for response in responses for call in response.tool_calls
    )
    baseline_instructions: tuple[str, ...] | None = None
    run_ids: list[str] = []

    for arm in ("baseline", "treatment"):
        workspace = prepare_evaluation_workspace(_CASE_ROOT, temporary_root=tmp_path)
        ledger = InMemoryEventLedger(run_id=f"run_scripted_skill_{arm}_{uuid4().hex}")
        provider = None
        if arm == "treatment":
            skill_workspace = Workspace(_SKILL_ROOT)
            catalog = await FileSkillCatalogLoader(skill_root=skill_workspace).load()
            provider = SkillContextBuilder(
                router=KeywordSkillRouter(catalog=catalog),
                loader=FileSkillLoader(skill_root=skill_workspace),
                event_ledger=ledger,
            )

        model = ScriptedModel(responses=responses)
        approver = FixtureApprover()
        agent = build_coding_agent(
            model=model,
            workspace=Workspace(workspace),
            process_runner=AsyncioProcessRunner(),
            event_ledger=ledger,
            approver=approver,
            skill_context_provider=provider,
            max_turns=manifest.budget.max_turns,
            max_tool_calls=manifest.budget.max_tool_calls,
        )
        result = await agent.run(task)

        assert result.stop_reason is StopReason.COMPLETED
        assert len(model.requests) == 5
        assert model.requests[-1].conversation == result.message_history
        assert model.requests[0].conversation == (
            Message(role=MessageRole.USER, content=task),
        )
        assert (
            tuple(item for item in result.message_history if isinstance(item, ToolCall))
            == expected_calls
        )
        assert approver.calls == [
            call for call in expected_calls if call.name in ("edit_file", "run_tests")
        ]
        errors = tuple(
            item.call_id
            for item in result.message_history
            if isinstance(item, ToolResult) and item.is_error
        )
        assert errors == (() if complete_fix else ("tests",))

        selection_events = tuple(
            event
            for event in ledger.events
            if event.kind is EventKind.SKILL_SELECTION_FINISHED
        )
        if arm == "baseline":
            baseline_instructions = tuple(model.requests[0].instructions)
            assert len(baseline_instructions) == 1
            assert selection_events == ()
        else:
            assert baseline_instructions is not None
            body = (
                (_SKILL_ROOT / "inventory-contract-review/SKILL.md")
                .read_text(encoding="utf-8")
                .strip()
            )
            assert len(selection_events) == 1
            assert tuple(
                selected["skill_name"]
                for selected in selection_events[0].payload["selected"]
            ) == ("inventory-contract-review",)
            assert tuple(model.requests[0].instructions) == baseline_instructions + (
                "# Loaded Skills\n\n## Skill: inventory-contract-review\n\n" + body,
            )
        assert all(
            request.instructions == model.requests[0].instructions
            for request in model.requests
        )
        assert tuple(
            item for item in result.message_history if isinstance(item, Message)
        ) == (Message(role=MessageRole.USER, content=task),)

        result_directory = tmp_path / arm
        result_directory.mkdir()
        answer_path = result_directory / "answer.txt"
        trace_path = result_directory / "trace.txt"
        output_path = result_directory / "result.json"
        answer_path.write_text(result.response.content, encoding="utf-8")
        _print_trace(ledger)
        trace_path.write_text(capsys.readouterr().err, encoding="utf-8")
        record_arguments = {
            "case_root": _CASE_ROOT,
            "workspace": workspace,
            "answer_path": answer_path,
            "trace_path": trace_path,
            "output_path": output_path,
            "model": "scripted-skill-task-v1",
            "agent_exit_code": 0,
        }
        if arm == "treatment":
            with pytest.raises(ValueError, match="requires --skill-arm"):
                record_result(**record_arguments)

        opposite_arm = "treatment" if arm == "baseline" else "baseline"
        with pytest.raises(ValueError, match="disagrees|requires one selection"):
            record_result(**record_arguments, skill_arm=opposite_arm)

        assert not output_path.exists()
        assert not (result_directory / "workspace.patch").exists()
        recorder_exit_code = record_evaluation_main(
            [
                "--case-root",
                str(_CASE_ROOT),
                "--workspace",
                str(workspace),
                "--answer",
                str(answer_path),
                "--trace",
                str(trace_path),
                "--output",
                str(output_path),
                "--model",
                "scripted-skill-task-v1",
                "--agent-exit-code",
                "0",
                "--skill-arm",
                arm,
            ]
        )
        assert capsys.readouterr().out.startswith("PASS " if complete_fix else "FAIL ")

        document = json.loads(output_path.read_text(encoding="utf-8"))
        assert (recorder_exit_code == 0) is complete_fix
        assert document["accepted"] is complete_fix
        assert document["verdict"] == {
            "outcome_passed": complete_fix,
            "operational_passed": True,
            "budget_passed": True,
            "trace_passed": complete_fix,
            "passed": complete_fix,
        }
        assert document["model"] == "scripted-skill-task-v1"
        assert document["skill_experiment"] == {
            "arm": arm,
            "selected_skill_names": (
                ["inventory-contract-review"] if arm == "treatment" else []
            ),
            "loaded_skill_names": (
                ["inventory-contract-review"] if arm == "treatment" else []
            ),
        }
        assert document["run"]["model_call_count"] == 5
        assert document["run"]["model_calls_with_usage"] == 0
        assert document["run"]["model_calls_missing_usage"] == 5
        assert document["run"]["usage_complete"] is False
        assert document["run"]["tool_execution_count"] == len(expected_calls)
        run_ids.append(document["run"]["run_id"])
        assert (
            parse_trace(trace_path.read_text(encoding="utf-8")).events == ledger.events
        )
        for artifact in document["artifacts"].values():
            path = result_directory / artifact["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    assert len(set(run_ids)) == 2
    assert summarize_evaluation_main([str(tmp_path), "--require-complete-usage"]) == 1
    summary = capsys.readouterr().out
    assert "- Runs with incomplete usage: 2" in summary
    assert "- Provider usage gate: FAIL" in summary
