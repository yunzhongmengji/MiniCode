import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from minicode.coding_agent import build_coding_agent
from minicode.core.checkpoints import InMemoryCheckpointStore
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.model import ModelResponse
from minicode.core.query_loop import RunResult, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.models.scripted import ScriptedModel
from minicode.tools.process import AsyncioProcessRunner
from minicode.workspace import Workspace

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REPAIR_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "large_search_context_repair"
)
_RECALL_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "large_search_context_recall"
)
_SUCCESSFUL_TRACE = """Trace run_001
001 tool_execution_finished {"outcome":"succeeded","tool_name":"list_files"}
002 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}
003 tool_execution_finished {"outcome":"succeeded","tool_name":"read_file"}
004 tool_execution_finished {"outcome":"succeeded","tool_name":"edit_file"}
005 tool_execution_finished {"outcome":"succeeded","tool_name":"run_tests"}
"""
_CORRECT_ANSWER = (
    "Fixed and tested the shared timeout.\n"
    "Evidence summary: 25 clients; "
    "first=accounting-ledger; last=transaction-journal.\n"
)


@dataclass(frozen=True, slots=True)
class _ScriptedArmRun:
    """Observable outputs from one deterministic comparison arm."""

    model: ScriptedModel
    result: RunResult
    event_ledger: InMemoryEventLedger
    workspace_root: Path
    acceptance: subprocess.CompletedProcess[str]


def _initialize_repository(workspace: Path) -> None:
    subprocess.run(("git", "init", "-q"), cwd=workspace, check=True)
    subprocess.run(("git", "add", "."), cwd=workspace, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=MiniCode Test",
            "-c",
            "user.email=minicode@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
        cwd=workspace,
        check=True,
    )


def _run_acceptance(
    workspace: Path,
    answer_path: Path,
    trace_path: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(_RECALL_CASE_ROOT / "acceptance.py"),
            str(workspace),
            str(answer_path),
            str(trace_path),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def _workspace_files(case_root: Path) -> dict[str, bytes]:
    workspace = case_root / "workspace"
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def _scripted_responses(*, read_back_history: bool) -> tuple[ModelResponse, ...]:
    responses = [
        ModelResponse(
            content="I will inspect the project.",
            tool_calls=(
                ToolCall(
                    call_id="call_list",
                    name="list_files",
                    arguments={"path": "."},
                ),
            ),
        ),
        ModelResponse(
            content="I will find the shared definition and callers.",
            tool_calls=(
                ToolCall(
                    call_id="call_search",
                    name="search_text",
                    arguments={
                        "query": "DEFAULT_REQUEST_TIMEOUT_SECONDS",
                        "path": ".",
                    },
                ),
            ),
        ),
        ModelResponse(
            content="I will read the canonical definition.",
            tool_calls=(
                ToolCall(
                    call_id="call_read",
                    name="read_file",
                    arguments={"path": "service_config/timeouts.py"},
                ),
            ),
        ),
        ModelResponse(
            content="I found the incorrect shared default.",
            tool_calls=(
                ToolCall(
                    call_id="call_edit",
                    name="edit_file",
                    arguments={
                        "path": "service_config/timeouts.py",
                        "old_text": "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
                        "new_text": "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
                    },
                ),
            ),
        ),
        ModelResponse(
            content="I will verify the shared fix.",
            tool_calls=(
                ToolCall(
                    call_id="call_test",
                    name="run_tests",
                    arguments={"path": "tests/test_timeouts.py"},
                ),
            ),
        ),
    ]

    if read_back_history:
        responses.append(
            ModelResponse(
                content="I need the exact earlier search evidence.",
                tool_calls=(
                    ToolCall(
                        call_id="call_restore_search",
                        name="read_tool_result",
                        arguments={"call_id": "call_search"},
                    ),
                ),
            )
        )

    responses.append(ModelResponse(content=_CORRECT_ANSWER))
    return tuple(responses)


def _trace_from_events(event_ledger: InMemoryEventLedger) -> str:
    lines = [f"Trace {event_ledger.run_id}"]

    for event in event_ledger.events:
        if event.kind is not EventKind.TOOL_EXECUTION_FINISHED:
            continue

        lines.append(
            f"{event.sequence:03d} tool_execution_finished "
            + json.dumps(
                {
                    "outcome": event.payload["outcome"],
                    "tool_name": event.payload["tool_name"],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    return "\n".join(lines) + "\n"


async def _run_scripted_arm(
    tmp_path: Path,
    *,
    arm: str,
    max_inline_tool_result_bytes: int | None,
    read_back_history: bool,
) -> _ScriptedArmRun:
    workspace_root = tmp_path / arm / "workspace"
    workspace_root.parent.mkdir()
    shutil.copytree(_RECALL_CASE_ROOT / "workspace", workspace_root)
    _initialize_repository(workspace_root)
    model = ScriptedModel(_scripted_responses(read_back_history=read_back_history))
    event_ledger = InMemoryEventLedger(run_id=f"run_recall_{arm}")
    checkpoint_store = InMemoryCheckpointStore()
    allow = PolicyDecision(
        outcome=PolicyOutcome.ALLOW,
        reason="allowed by deterministic recall comparison",
    )
    agent = build_coding_agent(
        model=model,
        workspace=Workspace(workspace_root),
        process_runner=AsyncioProcessRunner(),
        policy=ConfiguredToolPolicy(
            decisions={
                "list_files": allow,
                "search_text": allow,
                "read_file": allow,
                "edit_file": allow,
                "run_tests": allow,
                "read_tool_result": allow,
            }
        ),
        event_ledger=event_ledger,
        checkpoint_store=checkpoint_store,
        max_turns=9,
        max_tool_calls=9,
        max_inline_tool_result_bytes=max_inline_tool_result_bytes,
    )
    result = await agent.run(
        (_RECALL_CASE_ROOT / "task.txt").read_text(encoding="utf-8")
    )
    arm_root = workspace_root.parent
    answer_path = arm_root / "answer.txt"
    trace_path = arm_root / "trace.txt"
    answer_path.write_text(result.response.content, encoding="utf-8")
    trace_path.write_text(_trace_from_events(event_ledger), encoding="utf-8")

    return _ScriptedArmRun(
        model=model,
        result=result,
        event_ledger=event_ledger,
        workspace_root=workspace_root,
        acceptance=_run_acceptance(workspace_root, answer_path, trace_path),
    )


def _successful_tool_count(run: _ScriptedArmRun, tool_name: str) -> int:
    return sum(
        event.kind is EventKind.TOOL_EXECUTION_FINISHED
        and event.payload.get("tool_name") == tool_name
        and event.payload.get("outcome") == "succeeded"
        for event in run.event_ledger.events
    )


def test_recall_case_keeps_the_repair_workspace_identical() -> None:
    assert _workspace_files(_RECALL_CASE_ROOT) == _workspace_files(_REPAIR_CASE_ROOT)


def test_recall_case_requires_repair_and_exact_early_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(_RECALL_CASE_ROOT / "workspace", workspace)
    _initialize_repository(workspace)
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(_SUCCESSFUL_TRACE, encoding="utf-8")
    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    implementation_path = workspace / "service_config" / "timeouts.py"
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8").replace(
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
        ),
        encoding="utf-8",
    )
    answer_path.write_text(
        "Fixed, but I omitted the requested evidence.\n",
        encoding="utf-8",
    )

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")
    acceptance = _run_acceptance(workspace, answer_path, trace_path)

    assert acceptance.returncode == 0, acceptance.stderr
    assert acceptance.stdout.strip() == "PASS large_search_context_recall"


def test_recall_case_rejects_repeated_search(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(_RECALL_CASE_ROOT / "workspace", workspace)
    _initialize_repository(workspace)
    implementation_path = workspace / "service_config" / "timeouts.py"
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8").replace(
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
            "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
        ),
        encoding="utf-8",
    )
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    answer_path.write_text(_CORRECT_ANSWER, encoding="utf-8")
    trace_path.write_text(
        _SUCCESSFUL_TRACE
        + '006 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}\n',
        encoding="utf-8",
    )

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0


@pytest.mark.asyncio
async def test_baseline_and_projection_expose_evidence_before_answering(
    tmp_path: Path,
) -> None:
    baseline = await _run_scripted_arm(
        tmp_path,
        arm="baseline",
        max_inline_tool_result_bytes=None,
        read_back_history=False,
    )
    projection = await _run_scripted_arm(
        tmp_path,
        arm="projection",
        max_inline_tool_result_bytes=500,
        read_back_history=True,
    )

    for run in (baseline, projection):
        assert run.result.stop_reason is StopReason.COMPLETED
        assert run.result.response.content == _CORRECT_ANSWER
        assert run.acceptance.returncode == 0, run.acceptance.stderr
        assert run.acceptance.stdout.strip() == "PASS large_search_context_recall"
        assert _successful_tool_count(run, "search_text") == 1
        assert (
            (run.workspace_root / "service_config" / "timeouts.py")
            .read_text(encoding="utf-8")
            .endswith("DEFAULT_REQUEST_TIMEOUT_SECONDS = 30\n")
        )

    baseline_search_result = next(
        item
        for item in baseline.model.requests[-1].conversation
        if isinstance(item, ToolResult) and item.call_id == "call_search"
    )
    assert len(baseline_search_result.output.encode("utf-8")) == 2_730
    assert "accounting-ledger" in baseline_search_result.output
    assert "transaction-journal" in baseline_search_result.output
    assert _successful_tool_count(baseline, "read_tool_result") == 0

    projected_search_result = next(
        item
        for item in projection.model.requests[-1].conversation
        if isinstance(item, ToolResult) and item.call_id == "call_search"
    )
    assert json.loads(projected_search_result.output) == {
        "call_id": "call_search",
        "kind": "historical_tool_result_reference",
        "original_output_bytes": 2_730,
        "retrieval_tool": "read_tool_result",
    }
    restored_search_result = projection.model.requests[-1].conversation[-1]
    assert isinstance(restored_search_result, ToolResult)
    assert restored_search_result.call_id == "call_restore_search"
    assert restored_search_result.output == baseline_search_result.output
    assert _successful_tool_count(projection, "read_tool_result") == 1
