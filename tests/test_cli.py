import pytest

from minicode import cli
from minicode.core.checkpoints import RunCheckpoint
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)
from minicode.core.events import EventKind, InMemoryEventLedger
from minicode.core.file_checkpoint_store import FileCheckpointStore
from minicode.core.messages import Message, MessageRole
from minicode.core.model import (
    ModelConnectionError,
    ModelResponse,
)
from minicode.core.query_loop import RunResult, StopReason
from minicode.core.tool_calls import ToolCall
from minicode.models.scripted import ScriptedModel


def test_dry_run_reports_task_without_execution(capsys) -> None:
    exit_code = cli.main(["run", "修复测试", "--dry-run"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Task: 修复测试" in captured.out
    assert "Dry run: no files were changed." in captured.out


def test_run_executes_coding_task_and_prints_trace(monkeypatch, capsys) -> None:
    received_calls: list[tuple[str, int, int, int | None]] = []

    async def execute_coding_task(
        starting_input,
        *,
        max_turns: int,
        max_tool_calls: int,
        event_ledger,
        artifact_store,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
    ) -> RunResult:
        assert budgeted_context_configuration is None
        assert expected_model is None
        received_calls.append(
            (
                starting_input,
                max_turns,
                max_tool_calls,
                max_inline_tool_result_bytes,
            )
        )
        event_ledger.record(
            EventKind.RUN_STARTED,
            {"initial_history_items": 1},
        )
        event_ledger.record(
            EventKind.TOOL_EXECUTION_FINISHED,
            {
                "outcome": "succeeded",
                "output_artifact": {
                    "artifact_id": "sha256:test",
                    "media_type": "text/plain",
                    "byte_count": 12,
                },
            },
        )
        assert artifact_store is not None
        response = ModelResponse(
            content="测试已经修复。",
        )
        return RunResult(
            stop_reason=StopReason.COMPLETED,
            response=response,
            message_history=(
                Message(
                    role=MessageRole.USER,
                    content=starting_input,
                ),
            ),
            turns_used=1,
        )

    monkeypatch.setattr(
        cli,
        "_execute_coding_task",
        execute_coding_task,
    )

    exit_code = cli.main(
        [
            "run",
            "修复测试",
            "--trace",
            "--max-turns",
            "3",
            "--max-tool-calls",
            "4",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert received_calls == [
        (
            "修复测试",
            3,
            4,
            None,
        )
    ]
    assert captured.out == "测试已经修复。\n"
    assert "Run ID: run_" in captured.err
    assert "Trace run_" in captured.err
    assert '001 run_started {"initial_history_items": 1}' in captured.err
    assert '"artifact_id": "sha256:test"' in captured.err
    assert '"byte_count": 12' in captured.err


def test_run_reports_model_failure_with_trace(
    monkeypatch,
    capsys,
) -> None:
    async def execute_coding_task(
        starting_input,
        *,
        max_turns: int,
        max_tool_calls: int,
        event_ledger,
        artifact_store,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
    ) -> RunResult:
        del (
            starting_input,
            max_turns,
            max_tool_calls,
            artifact_store,
            max_inline_tool_result_bytes,
            budgeted_context_configuration,
            expected_model,
        )
        event_ledger.record(
            EventKind.RUN_STARTED,
            {},
        )
        event_ledger.record(
            EventKind.RUN_FINISHED,
            {
                "outcome": "failed",
                "error_type": ("ModelConnectionError"),
            },
        )
        raise ModelConnectionError("model service connection failed")

    monkeypatch.setattr(
        cli,
        "_execute_coding_task",
        execute_coding_task,
    )

    exit_code = cli.main(["run", "修复测试", "--trace"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert ("Model error: model service connection failed") in captured.err
    assert "001 run_started {}" in captured.err
    assert (
        '002 run_finished {"error_type": "ModelConnectionError", "outcome": "failed"}'
    ) in captured.err


def test_resume_loads_workspace_checkpoint_and_reuses_run_id(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(
            Message(
                role=MessageRole.USER,
                content="修复测试",
            ),
        ),
        turns_used=1,
        tool_calls_used=0,
    )
    state_home = tmp_path / "state"
    checkpoint_store = FileCheckpointStore(
        cli._checkpoint_root(
            tmp_path,
            {"XDG_STATE_HOME": str(state_home)},
        )
    )
    checkpoint_store.save(checkpoint)
    received_inputs = []

    async def execute_coding_task(
        starting_input,
        *,
        max_turns: int,
        max_tool_calls: int,
        event_ledger,
        artifact_store,
        max_inline_tool_result_bytes: int | None,
        budgeted_context_configuration,
        expected_model,
    ) -> RunResult:
        received_inputs.append(starting_input)
        assert max_inline_tool_result_bytes is None
        assert budgeted_context_configuration is None
        assert expected_model is None
        assert max_turns == 4
        assert max_tool_calls == 5
        assert event_ledger.run_id == "run_001"
        assert artifact_store is not None
        event_ledger.record(
            EventKind.RUN_RESUMED,
            {"turns_used": checkpoint.turns_used},
        )
        return RunResult(
            stop_reason=StopReason.COMPLETED,
            response=ModelResponse(
                content="恢复完成。",
            ),
            message_history=checkpoint.message_history,
            turns_used=2,
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(state_home),
    )
    monkeypatch.setattr(
        cli,
        "_execute_coding_task",
        execute_coding_task,
    )

    exit_code = cli.main(
        [
            "resume",
            "run_001",
            "--trace",
            "--max-turns",
            "4",
            "--max-tool-calls",
            "5",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert received_inputs == [checkpoint]
    assert captured.out == "恢复完成。\n"
    assert "Resuming Run ID: run_001" in captured.err
    assert "Trace run_001" in captured.err
    assert '001 run_resumed {"turns_used": 1}' in captured.err


def test_completed_run_is_persisted_and_cli_refuses_to_resume(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    class RecordingClient:
        async def close(self) -> None:
            pass

    model = ScriptedModel(
        responses=[
            ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        call_id="call_001",
                        name="read_file",
                        arguments={"path": "README.md"},
                    ),
                ),
            ),
            ModelResponse(content="README inspected."),
        ]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-api-key")
    monkeypatch.setattr(cli, "build_dashscope_client", lambda config: RecordingClient())
    monkeypatch.setattr(cli, "build_dashscope_model", lambda config, *, client: model)
    (tmp_path / "README.md").write_text("Project description.\n", encoding="utf-8")

    assert cli.main(["run", "Inspect README.md."]) == 0
    initial_output = capsys.readouterr()
    run_id = initial_output.err.strip().removeprefix("Run ID: ")
    store = FileCheckpointStore(
        cli._checkpoint_root(tmp_path, {"XDG_STATE_HOME": str(tmp_path / "state")})
    )
    checkpoint = store.latest(run_id)
    assert checkpoint is not None
    assert checkpoint.is_completed is True
    assert checkpoint.turns_used == 2
    assert checkpoint.tool_calls_used == 1

    def unexpected_execution(*args, **kwargs):
        pytest.fail("completed run must be rejected before agent execution")

    monkeypatch.delenv("DASHSCOPE_API_KEY")
    monkeypatch.setattr(cli, "_execute_coding_task", unexpected_execution)

    assert cli.main(["resume", run_id]) == 2
    resumed_output = capsys.readouterr()
    assert resumed_output.out == ""
    assert resumed_output.err == (
        f"Checkpoint error: run {run_id} is already completed; cannot resume\n"
    )
    assert store.latest(run_id) == checkpoint
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_run_coding_task_closes_client_when_agent_fails(
    monkeypatch,
    tmp_path,
) -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FailingAgent:
        async def run(self, task: str) -> RunResult:
            del task
            raise RuntimeError("simulated agent failure")

    client = RecordingClient()
    model = object()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "DASHSCOPE_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(tmp_path / "state"),
    )
    monkeypatch.setattr(
        cli,
        "build_dashscope_client",
        lambda config: client,
    )
    monkeypatch.setattr(
        cli,
        "build_dashscope_model",
        lambda config, *, client: model,
    )
    received_options = {}

    def build_agent(**options):
        received_options.update(options)
        return FailingAgent()

    monkeypatch.setattr(
        cli,
        "build_coding_agent",
        build_agent,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated agent failure",
    ):
        await cli._execute_coding_task(
            "修复测试",
            max_turns=8,
            max_tool_calls=8,
            event_ledger=InMemoryEventLedger(
                run_id="run_001",
            ),
        )

    assert client.closed is True
    assert isinstance(
        received_options["checkpoint_store"],
        FileCheckpointStore,
    )


@pytest.mark.asyncio
async def test_execute_coding_task_applies_benchmark_projection_threshold(
    monkeypatch,
    tmp_path,
) -> None:
    class RecordingClient:
        async def close(self) -> None:
            return None

    baseline_model = ScriptedModel([ModelResponse(content="baseline complete")])
    projected_model = ScriptedModel([ModelResponse(content="projection complete")])
    models = iter((baseline_model, projected_model))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-api-key")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(
        cli,
        "build_dashscope_client",
        lambda config: RecordingClient(),
    )
    monkeypatch.setattr(
        cli,
        "build_dashscope_model",
        lambda config, *, client: next(models),
    )

    await cli._execute_coding_task(
        "Complete the baseline run.",
        max_turns=1,
        max_tool_calls=1,
        event_ledger=InMemoryEventLedger(run_id="run_baseline"),
    )
    await cli._execute_coding_task(
        "Complete the projected run.",
        max_turns=1,
        max_tool_calls=1,
        event_ledger=InMemoryEventLedger(run_id="run_projection"),
        max_inline_tool_result_bytes=500,
    )

    baseline_tool_names = {
        tool_spec.name for tool_spec in baseline_model.requests[0].tool_specs
    }
    projected_tool_names = {
        tool_spec.name for tool_spec in projected_model.requests[0].tool_specs
    }
    assert "read_tool_result" not in baseline_tool_names
    assert projected_tool_names == baseline_tool_names


@pytest.mark.asyncio
async def test_execute_coding_task_applies_registered_budget_configuration(
    monkeypatch,
    tmp_path,
) -> None:
    class RecordingClient:
        async def close(self) -> None:
            return None

    class RecordingAgent:
        async def run(self, task: str) -> RunResult:
            return RunResult(
                stop_reason=StopReason.COMPLETED,
                response=ModelResponse(content="complete"),
                message_history=(
                    Message(role=MessageRole.USER, content=task),
                ),
                turns_used=1,
            )

    configuration = BudgetedContextProjectionConfiguration(
        max_request_bytes=10_000,
        protected_recent_batch_count=2,
        minimum_net_savings_bytes=1,
        excluded_tool_names=("git_diff", "run_tests"),
        max_retrievable_output_bytes=50_000,
    )
    received_options = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-api-key")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "build_dashscope_client", lambda config: RecordingClient())
    monkeypatch.setattr(
        cli,
        "build_dashscope_model",
        lambda config, *, client: object(),
    )

    def build_agent(**options):
        received_options.update(options)
        return RecordingAgent()

    monkeypatch.setattr(cli, "build_coding_agent", build_agent)

    await cli._execute_coding_task(
        "Complete the registered run.",
        max_turns=1,
        max_tool_calls=1,
        event_ledger=InMemoryEventLedger(run_id="run_registered"),
        budgeted_context_configuration=configuration,
        expected_model="qwen3.7-flash-2026-07-15",
    )

    assert received_options["max_inline_tool_result_bytes"] is None
    assert received_options["budgeted_context_configuration"] == configuration


@pytest.mark.asyncio
async def test_execute_coding_task_rejects_registered_model_drift_before_client(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-api-key")
    monkeypatch.setenv("DASHSCOPE_MODEL", "different-model")

    def unexpected_client(config):
        pytest.fail("model drift must be rejected before creating a client")

    monkeypatch.setattr(cli, "build_dashscope_client", unexpected_client)

    with pytest.raises(
        cli._CliConfigurationError,
        match="configured model does not match the registered experiment",
    ):
        await cli._execute_coding_task(
            "Do not run.",
            max_turns=1,
            max_tool_calls=1,
            event_ledger=InMemoryEventLedger(run_id="run_model_drift"),
            expected_model="qwen3.7-flash-2026-07-15",
        )


@pytest.mark.asyncio
async def test_execute_coding_task_delegates_checkpoint_to_agent_resume(
    monkeypatch,
    tmp_path,
) -> None:
    class RecordingClient:
        async def close(self) -> None:
            return None

    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(),
        turns_used=1,
        tool_calls_used=0,
    )
    received_checkpoints = []

    class RecordingAgent:
        async def resume(self, received: RunCheckpoint) -> RunResult:
            received_checkpoints.append(received)
            return RunResult(
                stop_reason=StopReason.COMPLETED,
                response=ModelResponse(
                    content="恢复完成。",
                ),
                message_history=(),
                turns_used=2,
            )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "DASHSCOPE_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(tmp_path / "state"),
    )
    monkeypatch.setattr(
        cli,
        "build_dashscope_client",
        lambda config: RecordingClient(),
    )
    monkeypatch.setattr(
        cli,
        "build_dashscope_model",
        lambda config, *, client: object(),
    )
    monkeypatch.setattr(
        cli,
        "build_coding_agent",
        lambda **options: RecordingAgent(),
    )

    result = await cli._execute_coding_task(
        checkpoint,
        max_turns=8,
        max_tool_calls=8,
        event_ledger=InMemoryEventLedger(
            run_id="run_001",
        ),
    )

    assert result.response.content == "恢复完成。"
    assert received_checkpoints == [checkpoint]


def test_missing_command_exits_with_usage_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "the following arguments are required" in captured.err
