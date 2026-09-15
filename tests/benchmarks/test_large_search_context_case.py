import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from minicode.core.checkpoints import InMemoryCheckpointStore
from minicode.core.context_profile import profile_context_projection
from minicode.core.context_projection import ToolResultReferenceProjector
from minicode.core.context_retrieval import RunToolResultSource
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.read_tool_result import ReadToolResultTool
from minicode.tools.search_text import SearchTextArguments, SearchTextTool
from minicode.workspace import Workspace

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CASE_ROOT = (
    _PROJECT_ROOT
    / "benchmarks"
    / "coding_agent"
    / "cases"
    / "large_search_context_repair"
)
_SUCCESSFUL_TRACE = """Trace run_001
001 tool_execution_finished {"outcome":"succeeded","tool_name":"list_files"}
002 tool_execution_finished {"outcome":"succeeded","tool_name":"search_text"}
003 tool_execution_finished {"outcome":"succeeded","tool_name":"read_file"}
004 tool_execution_finished {"outcome":"succeeded","tool_name":"edit_file"}
005 tool_execution_finished {"outcome":"succeeded","tool_name":"run_tests"}
"""


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
            str(_CASE_ROOT / "acceptance.py"),
            str(workspace),
            str(answer_path),
            str(trace_path),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def test_large_search_context_case_rejects_bug_and_accepts_shared_fix(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(_CASE_ROOT / "workspace", workspace)
    _initialize_repository(workspace)
    answer_path = tmp_path / "answer.txt"
    trace_path = tmp_path / "trace.txt"
    answer_path.write_text("Fixed the shared timeout.", encoding="utf-8")
    trace_path.write_text(_SUCCESSFUL_TRACE, encoding="utf-8")

    assert _run_acceptance(workspace, answer_path, trace_path).returncode != 0

    implementation_path = workspace / "service_config" / "timeouts.py"
    original = implementation_path.read_text(encoding="utf-8")
    fixed = original.replace(
        "DEFAULT_REQUEST_TIMEOUT_SECONDS = 3",
        "DEFAULT_REQUEST_TIMEOUT_SECONDS = 30",
    )
    assert fixed != original
    implementation_path.write_text(fixed, encoding="utf-8")

    acceptance = _run_acceptance(workspace, answer_path, trace_path)

    assert acceptance.returncode == 0, acceptance.stderr
    assert acceptance.stdout.strip() == "PASS large_search_context_repair"


@pytest.mark.asyncio
async def test_large_search_result_has_positive_projection_net_savings() -> None:
    workspace = Workspace(root=_CASE_ROOT / "workspace")
    search_output = await SearchTextTool(workspace).execute(
        SearchTextArguments(
            query="DEFAULT_REQUEST_TIMEOUT_SECONDS",
            path=".",
        )
    )
    search_result = ToolResult(
        call_id="call_search",
        output=search_output,
    )
    latest_result = ToolResult(
        call_id="call_read",
        output='File "service_config/timeouts.py":\nDEFAULT_REQUEST_TIMEOUT_SECONDS = 3',
    )
    request = ModelRequest(
        conversation=(
            ToolCall(
                call_id="call_search",
                name="search_text",
                arguments={
                    "query": "DEFAULT_REQUEST_TIMEOUT_SECONDS",
                    "path": ".",
                },
            ),
            search_result,
            Message(
                role=MessageRole.ASSISTANT,
                content="I will read the canonical definition.",
            ),
            ToolCall(
                call_id="call_read",
                name="read_file",
                arguments={"path": "service_config/timeouts.py"},
            ),
            latest_result,
        )
    )
    retrieval_tool = ReadToolResultTool(
        RunToolResultSource(
            InMemoryCheckpointStore(),
            run_id="run_001",
        )
    )
    projected = await ToolResultReferenceProjector(
        max_inline_output_bytes=500,
        retrieval_tool_spec=retrieval_tool.spec,
    ).project(request)
    profile = profile_context_projection(request, projected)

    assert len(search_output.encode("utf-8")) > 2_000
    assert projected is not request
    assert profile.changed_tool_result_count == 1
    assert profile.total_bytes_saved > 0
    assert tuple(spec.name for spec in projected.tool_specs) == ("read_tool_result",)
