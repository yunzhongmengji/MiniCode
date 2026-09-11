import pytest

from minicode import cli
from minicode.core.events import EventKind
from minicode.core.messages import Message, MessageRole
from minicode.core.model import (
    ModelConnectionError,
    ModelResponse,
)
from minicode.core.query_loop import RunResult, StopReason


def test_dry_run_reports_task_without_execution(capsys) -> None:
    exit_code = cli.main(["run", "修复测试", "--dry-run"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Task: 修复测试" in captured.out
    assert "Dry run: no files were changed." in captured.out


def test_run_executes_coding_task_and_prints_trace(monkeypatch, capsys) -> None:
    received_calls: list[tuple[str, int, int]] = []

    async def run_coding_task(
        task: str,
        *,
        max_turns: int,
        max_tool_calls: int,
        event_ledger,
        artifact_store,
    ) -> RunResult:
        received_calls.append(
            (
                task,
                max_turns,
                max_tool_calls,
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
                    content=task,
                ),
            ),
            turns_used=1,
        )

    monkeypatch.setattr(
        cli,
        "_run_coding_task",
        run_coding_task,
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
        )
    ]
    assert captured.out == "测试已经修复。\n"
    assert "Trace run_" in captured.err
    assert '001 run_started {"initial_history_items": 1}' in captured.err
    assert '"artifact_id": "sha256:test"' in captured.err
    assert '"byte_count": 12' in captured.err


def test_run_reports_model_failure_with_trace(
    monkeypatch,
    capsys,
) -> None:
    async def run_coding_task(
        task: str,
        *,
        max_turns: int,
        max_tool_calls: int,
        event_ledger,
        artifact_store,
    ) -> RunResult:
        del task, max_turns, max_tool_calls, artifact_store
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
        "_run_coding_task",
        run_coding_task,
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
    monkeypatch.setattr(
        cli,
        "build_coding_agent",
        lambda **options: FailingAgent(),
    )

    with pytest.raises(
        RuntimeError,
        match="simulated agent failure",
    ):
        await cli._run_coding_task(
            "修复测试",
            max_turns=8,
            max_tool_calls=8,
        )

    assert client.closed is True


def test_missing_command_exits_with_usage_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "the following arguments are required" in captured.err
