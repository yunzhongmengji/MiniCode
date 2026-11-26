"""Tests for the unified thin CLI reusing RecoverableAgentRuntime and SQLite storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from minicode.cli import _dispatch_async, build_parser
from minicode.models import ModelResponse, ScriptedModel
from minicode.schemas import TokenUsage


@pytest.mark.asyncio
async def test_cli_run_and_replay_share_sqlite_runtime(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli.sqlite3"
    parser = build_parser()

    run_args = parser.parse_args(
        [
            "--workspace",
            str(tmp_path),
            "--db",
            str(db_path),
            "run",
            "Summarize workspace",
            "--session-id",
            "cli_sess_1",
        ]
    )
    exit_code = await _dispatch_async(
        run_args,
        model_factory=lambda: ScriptedModel(
            (
                ModelResponse(
                    content="Workspace checked cleanly.",
                    usage=TokenUsage(input_tokens=40, output_tokens=12),
                ),
            )
        ),
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "session_id: cli_sess_1" in out
    assert "Workspace checked cleanly." in out

    replay_args = parser.parse_args(
        [
            "--workspace",
            str(tmp_path),
            "--db",
            str(db_path),
            "replay",
            "cli_sess_1",
        ]
    )
    assert await _dispatch_async(replay_args) == 0
    replay_out = capsys.readouterr().out
    assert "Session Replay: cli_sess_1" in replay_out
    assert "Status: completed" in replay_out
