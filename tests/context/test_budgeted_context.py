"""Tests for budget-driven dual-view context compression and read_artifact retrieval."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from minicode.context import (
    READ_ARTIFACT_TOOL_NAME,
    ApproximateTokenEstimator,
    BudgetedContextManager,
    ContextBudgetConfig,
    ReadArtifactArguments,
    ReadArtifactTool,
)
from minicode.models import ModelRequest, ModelResponse
from minicode.runtime import RecoverableAgentRuntime
from minicode.schemas import (
    EventType,
    SessionStatus,
    TokenUsage,
    ToolCallRecord,
    ToolResultRecord,
)
from minicode.storage import SqliteRuntimeStorage
from minicode.tools.base import ToolExecutionError
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec

_REF_PATTERN = re.compile(r"\[Ref: event_id=(\d+), tool=([a-zA-Z0-9_]+), summary=\"")


class _PathArgs(ToolArguments):
    path: str


class _FunctionTool:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        arguments_type: type[ToolArguments],
        handler: Callable[[ToolArguments], Awaitable[str]],
    ) -> None:
        self._spec = ToolSpec(
            name=name,
            description=description,
            arguments_type=arguments_type,
        )
        self._handler = handler

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        return await self._handler(arguments)


class _AdaptiveRecallModel:
    """Fake model that records every request and dynamically recalls compressed refs."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self._turn = 0
        self.recalled_event_id: int | None = None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        self._turn += 1

        if self._turn == 1:
            return ModelResponse(
                content="Step 1: read large_module.py",
                tool_calls=(
                    ToolCallRecord(
                        call_id="call_read_1",
                        name="read_file",
                        arguments={"path": "large_module.py"},
                    ),
                ),
                usage=TokenUsage(input_tokens=80, output_tokens=20),
            )

        if self._turn == 2:
            return ModelResponse(
                content="Step 2: read test_logs.txt",
                tool_calls=(
                    ToolCallRecord(
                        call_id="call_read_2",
                        name="read_file",
                        arguments={"path": "test_logs.txt"},
                    ),
                ),
                usage=TokenUsage(input_tokens=600, output_tokens=20),
            )

        if self._turn == 3:
            # Verify the older large_module.py output was replaced with a Ref placeholder.
            tool_results = [
                item
                for item in request.conversation
                if isinstance(item, ToolResultRecord)
            ]
            first_result = next(
                res for res in tool_results if res.call_id == "call_read_1"
            )
            match = _REF_PATTERN.search(first_result.output)
            assert match is not None, (
                f"Expected compressed Ref placeholder, got: {first_result.output[:120]}"
            )
            event_id = int(match.group(1))
            self.recalled_event_id = event_id
            return ModelResponse(
                content="Step 3: recall compressed large_module.py via read_artifact",
                tool_calls=(
                    ToolCallRecord(
                        call_id="call_recall_1",
                        name=READ_ARTIFACT_TOOL_NAME,
                        arguments={"event_id": event_id},
                    ),
                ),
                usage=TokenUsage(input_tokens=500, output_tokens=25),
            )

        # Turn 4: verify read_artifact returned the exact uncompressed marker.
        recalled_result = next(
            item
            for item in request.conversation
            if isinstance(item, ToolResultRecord) and item.call_id == "call_recall_1"
        )
        assert "SECRET_MARKER_42 = 'alpha-99'" in recalled_result.output
        return ModelResponse(
            content="Found SECRET_MARKER_42 = 'alpha-99' after artifact recall.",
            usage=TokenUsage(input_tokens=520, output_tokens=18),
        )


@pytest.mark.asyncio
async def test_long_chain_stays_within_token_budget_and_recalls_artifact(
    tmp_path: Path,
) -> None:
    """Verify dual-view compression stays under budget and read_artifact restores full text."""
    db_path = tmp_path / "context_budget.sqlite3"
    large_module_body = (
        "HEADER: large_module.py\n"
        + ("def helper_padding_function() -> int:\n    return 123456789\n" * 30)
        + "SECRET_MARKER_42 = 'alpha-99'\n"
        + ("# trailing documentation line for budget testing\n" * 20)
    )
    large_test_log = (
        "PYTEST LOG START\n"
        + ("PASSED tests/test_suite.py::test_case_padding_output_line\n" * 40)
        + "PYTEST LOG END\n"
    )
    files = {
        "large_module.py": large_module_body,
        "test_logs.txt": large_test_log,
    }

    async def handle_read(args: ToolArguments) -> str:
        assert isinstance(args, _PathArgs)
        return files[args.path]

    registry = ToolRegistry()
    registry.register(
        _FunctionTool(
            name="read_file",
            description="Read a file.",
            arguments_type=_PathArgs,
            handler=handle_read,
        )
    )

    storage = SqliteRuntimeStorage(db_path)
    try:
        estimator = ApproximateTokenEstimator()
        max_budget = 1100
        context_manager = BudgetedContextManager(
            event_ledger=storage.event_ledger,
            config=ContextBudgetConfig(
                max_context_tokens=max_budget,
                protected_recent_tool_results=1,
                min_compress_tokens=24,
                summary_max_chars=64,
            ),
            estimator=estimator,
        )
        model = _AdaptiveRecallModel()
        runtime = RecoverableAgentRuntime(
            model=model,
            tool_registry=registry,
            storage=storage,
            context_manager=context_manager,
            max_turns=6,
        )

        result = await runtime.start(
            "Inspect large_module.py and test_logs.txt, then confirm SECRET_MARKER_42.",
            session_id="sess_ctx_1",
        )
        assert result.status is SessionStatus.COMPLETED
        assert result.final_answer == (
            "Found SECRET_MARKER_42 = 'alpha-99' after artifact recall."
        )
        assert model.recalled_event_id is not None
        assert len(model.requests) == 4

        # Check every turn's recorded visible context tokens stayed within budget.
        reasoning_events = [
            ev
            for ev in storage.event_ledger.list_events("sess_ctx_1")
            if ev.event_type is EventType.REASONING_COMPLETED
        ]
        assert len(reasoning_events) == 4

        for ev in reasoning_events:
            visible_tokens = ev.payload["visible_context_tokens"]
            assert isinstance(visible_tokens, int)
            assert visible_tokens <= max_budget

        # Turn 3 and Turn 4 must have compressed older oversized tool results.
        turn3_payload = reasoning_events[2].payload
        assert turn3_payload["original_context_tokens"] > max_budget
        assert turn3_payload["compressed_event_ids"] == [model.recalled_event_id]

        # Dual-view invariant: Full History in checkpoint & ledger remains uncompressed!
        latest_cp = storage.checkpoint_store.load_latest("sess_ctx_1")
        assert latest_cp is not None
        stored_read_1 = next(
            entry
            for entry in latest_cp.history
            if isinstance(entry, ToolResultRecord) and entry.call_id == "call_read_1"
        )
        assert stored_read_1.output == large_module_body
        assert "[Ref:" not in stored_read_1.output
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_read_artifact_enforces_session_isolation_and_supports_slicing(
    tmp_path: Path,
) -> None:
    """read_artifact must isolate sessions and support offset/max_chars slicing."""
    db_path = tmp_path / "artifact_isolation.sqlite3"
    storage = SqliteRuntimeStorage(db_path)
    try:
        from minicode.schemas import LedgerEventInput

        ev_start = storage.event_ledger.append(
            session_id="sess_a",
            step=0,
            event=LedgerEventInput(
                event_type=EventType.SESSION_STARTED,
                payload={"task": "alpha"},
            ),
        )
        ev_tool = storage.event_ledger.append(
            session_id="sess_a",
            step=1,
            event=LedgerEventInput(
                event_type=EventType.TOOL_EXECUTED,
                payload={
                    "call_id": "c1",
                    "tool_name": "read_file",
                    "output": "0123456789ABCDEF",
                    "is_error": False,
                },
            ),
        )
        assert ev_start.event_id is not None
        assert ev_tool.event_id is not None

        tool_a = ReadArtifactTool(
            event_ledger=storage.event_ledger,
            session_id="sess_a",
        )
        assert (
            await tool_a.execute(ReadArtifactArguments(event_id=ev_tool.event_id))
            == "0123456789ABCDEF"
        )
        assert (
            await tool_a.execute(
                ReadArtifactArguments(
                    event_id=ev_tool.event_id,
                    offset_chars=4,
                    max_chars=6,
                )
            )
            == "456789"
        )

        # Non-tool events cannot be read as artifacts.
        with pytest.raises(ToolExecutionError, match="not a tool_executed event"):
            await tool_a.execute(ReadArtifactArguments(event_id=ev_start.event_id))

        # Another session cannot read sess_a's artifact event_id.
        tool_b = ReadArtifactTool(
            event_ledger=storage.event_ledger,
            session_id="sess_b",
        )
        with pytest.raises(ToolExecutionError, match="not found in session 'sess_b'"):
            await tool_b.execute(ReadArtifactArguments(event_id=ev_tool.event_id))
    finally:
        storage.close()
