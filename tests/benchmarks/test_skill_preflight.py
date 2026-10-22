"""Run the frozen pair through CLI, real tools, and the result recorder offline."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from minicode import cli
from minicode.core.model import ModelQuotaExceededError, ModelResponse, ModelUsage
from minicode.core.tool_calls import ToolCall
from minicode.models.scripted import ScriptedModel
from minicode.skill_preflight import (
    FixtureToolApprover,
    SkillPreflightProtocol,
    execute_skill_preflight,
    prepare_skill_preflight,
)

_ROOT = Path(__file__).resolve().parents[2]


def _protocol() -> SkillPreflightProtocol:
    return SkillPreflightProtocol.model_validate_json(
        (_ROOT / "benchmarks/skill_task_comparison/v1/preflight.json").read_text()
    )


def test_current_protocol_uses_requested_alias_without_changing_budgets() -> None:
    protocol = _protocol()
    assert protocol.protocol_id == "skill-inventory-preflight-v2-qwen3.7-flash"
    assert protocol.model == "qwen3.7-flash"
    assert protocol.token_budget().max_input_tokens == 30000
    assert protocol.token_budget().max_output_tokens == 4096
    assert protocol.token_budget().max_response_output_tokens == 1024
    assert protocol.model_max_retries == 0
    assert protocol.arm_order == ("baseline", "treatment")


def _responses() -> tuple[ModelResponse, ...]:
    usage = ModelUsage(600, 20)
    return (
        ModelResponse(
            content="",
            usage=usage,
            tool_calls=tuple(
                ToolCall(
                    call_id=f"read_{i}", name="read_file", arguments={"path": path}
                )
                for i, path in enumerate(
                    ("inventory.py", "report.py", "tests/test_inventory_contract.py")
                )
            ),
        ),
        ModelResponse(
            content="",
            usage=usage,
            tool_calls=(
                ToolCall(
                    call_id="edit_inventory",
                    name="edit_file",
                    arguments={
                        "path": "inventory.py",
                        "old_text": '"quantity": stock',
                        "new_text": '"stock": stock',
                    },
                ),
                ToolCall(
                    call_id="edit_report",
                    name="edit_file",
                    arguments={
                        "path": "report.py",
                        "old_text": "record['quantity']",
                        "new_text": "record['stock']",
                    },
                ),
            ),
        ),
        ModelResponse(
            content="",
            usage=usage,
            tool_calls=(
                ToolCall(
                    call_id="tests", name="run_tests", arguments={"path": "tests"}
                ),
            ),
        ),
        ModelResponse(content="Fixture repaired.", usage=usage),
    )


def _fake_provider(monkeypatch, tmp_path, responses):
    models = []
    clients = []
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-test-key")
    monkeypatch.setenv("DASHSCOPE_MODEL", _protocol().model)
    monkeypatch.setenv("DASHSCOPE_BASE_URL", _protocol().base_url)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def build_client(config, *, max_retries):
        assert max_retries == 0
        client = AsyncMock()
        clients.append(client)
        return client

    def build_model(config, *, client, max_output_tokens):
        assert config.model == _protocol().model
        assert max_output_tokens == 1024
        model = ScriptedModel(responses=responses)
        models.append(model)
        return model

    monkeypatch.setattr(cli, "build_dashscope_client", build_client)
    monkeypatch.setattr(cli, "build_dashscope_model", build_model)
    return models, clients


def test_prepare_is_offline_and_preserves_exact_source_snapshot(
    tmp_path, monkeypatch
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("preparation must not construct a provider")

    monkeypatch.setattr(cli, "build_dashscope_client", forbidden)
    root = prepare_skill_preflight(tmp_path / "pair")
    plan = json.loads((root / "plan.json").read_text())
    assert plan["max_model_requests"] == 16
    assert plan["run_attempts_per_arm"] == 1
    assert plan["protocol"]["model_max_retries"] == 0
    original = _ROOT / "src/minicode/core/query_loop.py"
    assert (
        root / "snapshot/src/minicode/core/query_loop.py"
    ).read_bytes() == original.read_bytes()
    assert not (root / "execution.started").exists()
    with pytest.raises(FileExistsError):
        prepare_skill_preflight(root)


def test_real_pair_path_runs_two_isolated_scripted_arms_and_records_usage(
    tmp_path, monkeypatch
) -> None:
    models, clients = _fake_provider(monkeypatch, tmp_path, _responses())
    root = prepare_skill_preflight(tmp_path / "pair")
    assert execute_skill_preflight(root) is True
    assert len(models) == 2
    assert all(len(model.calls) == 4 for model in models)
    assert models[0].requests[0].conversation == models[1].requests[0].conversation
    assert len(models[0].requests[0].instructions) == 1
    assert len(models[1].requests[0].instructions) == 2
    results = []
    for arm in ("baseline", "treatment"):
        result = json.loads((root / arm / "result.json").read_text())
        results.append(result)
        assert result["verdict"]["passed"] is True
        assert result["run"]["usage_complete"] is True
        assert result["run"]["input_tokens"] == 2400
        assert result["run"]["model_budget"]["max_input_tokens"] == 30000
        assert result["skill_experiment"]["arm"] == arm
        assert (root / arm / "workspace.patch").is_file()
    assert results[0]["run"]["run_id"] != results[1]["run"]["run_id"]
    assert (root / "baseline/workspace.path").read_text() != (
        root / "treatment/workspace.path"
    ).read_text()
    assert json.loads((root / "batch.json").read_text())["pair_complete"] is True
    for client in clients:
        client.close.assert_awaited_once()
    with pytest.raises(FileExistsError):
        execute_skill_preflight(root)
    assert len(models) == 2


@pytest.mark.parametrize(
    "usage, stop_reason",
    [(None, "usage_missing"), (ModelUsage(30000, 1), "token_budget")],
)
def test_first_run_stop_prevents_treatment_and_retains_failure(
    tmp_path, monkeypatch, usage, stop_reason
) -> None:
    responses = (
        ModelResponse(content="", tool_calls=_responses()[0].tool_calls, usage=usage),
        *_responses(),
    )
    models, _ = _fake_provider(monkeypatch, tmp_path, responses)
    root = prepare_skill_preflight(tmp_path / "pair")
    assert execute_skill_preflight(root) is False
    assert len(models) == 1
    assert len(models[0].calls) == 1
    assert not (root / "treatment").exists()
    result = json.loads((root / "baseline/result.json").read_text())
    assert result["run"]["stop_reason"] == stop_reason
    assert result["verdict"]["passed"] is False
    assert result["run"]["tool_execution_count"] == 0
    assert json.loads((root / "batch.json").read_text())["pair_complete"] is False


def test_task_failure_does_not_hide_the_other_arm(tmp_path, monkeypatch) -> None:
    models, _ = _fake_provider(
        monkeypatch,
        tmp_path,
        [ModelResponse(content="Not fixed", usage=ModelUsage(10, 1))],
    )
    root = prepare_skill_preflight(tmp_path / "pair")
    assert execute_skill_preflight(root) is True
    assert len(models) == 2
    batch = json.loads((root / "batch.json").read_text())
    assert all(run["task_passed"] is False for run in batch["runs"])


def test_provider_quota_error_is_recorded_without_treatment_or_retry(
    tmp_path, monkeypatch
) -> None:
    _, clients = _fake_provider(monkeypatch, tmp_path, [])
    failed_model = AsyncMock()
    failed_model.complete.side_effect = ModelQuotaExceededError(
        "model free quota exhausted"
    )
    monkeypatch.setattr(
        cli, "build_dashscope_model", lambda *args, **kwargs: failed_model
    )
    root = prepare_skill_preflight(tmp_path / "pair")
    assert execute_skill_preflight(root) is False
    failed_model.complete.assert_awaited_once()
    assert len(clients) == 1
    clients[0].close.assert_awaited_once()
    assert not (root / "treatment").exists()
    result = json.loads((root / "baseline/result.json").read_text())
    assert result["run"]["outcome"] == "failed"
    assert result["run"]["model_call_count"] == 1
    assert result["run"]["tool_execution_count"] == 0
    assert result["run"]["usage_complete"] is False
    assert "ModelQuotaExceededError" in (root / "baseline/trace.txt").read_text()
    assert (root / "baseline/workspace.patch").read_text() == ""


@pytest.mark.parametrize("model", ["wrong-model", "qwen3.7-flash-2026-07-15"])
def test_provider_mismatch_rejected_before_client_creation(
    tmp_path, monkeypatch, model
) -> None:
    models, _ = _fake_provider(monkeypatch, tmp_path, _responses())
    root = prepare_skill_preflight(tmp_path / "pair")
    monkeypatch.setenv("DASHSCOPE_MODEL", model)
    with pytest.raises(ValueError, match="configured model/base_url"):
        execute_skill_preflight(root)
    assert models == []
    assert not (root / "execution.started").exists()


def test_snapshot_change_rejected_before_provider_creation(
    tmp_path, monkeypatch
) -> None:
    models, _ = _fake_provider(monkeypatch, tmp_path, _responses())
    root = prepare_skill_preflight(tmp_path / "pair")
    (root / "snapshot/src/minicode/core/query_loop.py").write_text("tampered")
    with pytest.raises(ValueError, match="snapshot changed"):
        execute_skill_preflight(root)
    assert models == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, path, allowed",
    [
        ("edit_file", "inventory.py", True),
        ("edit_file", "./report.py", True),
        ("edit_file", "tests/test_inventory_contract.py", False),
        ("edit_file", "../outside.py", False),
        ("create_file", "inventory.py", False),
        ("run_tests", "tests", True),
        ("run_tests", "tests/test_inventory_contract.py", True),
        ("run_tests", "inventory.py", False),
    ],
)
async def test_fixture_approval_scope(tmp_path, name, path, allowed) -> None:
    call = ToolCall(call_id="scope", name=name, arguments={"path": path})
    assert (
        await FixtureToolApprover(tmp_path, _protocol()).request_approval(
            call, reason="fixture"
        )
        is allowed
    )
