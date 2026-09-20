import json
from pathlib import Path

import pytest

from minicode.context_experiment_protocol import (
    load_budgeted_context_experiment_protocol,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROTOCOL_PATH = (
    _PROJECT_ROOT / "benchmarks" / "context_projection" / "real_model_protocol_v4.json"
)


def test_registered_v4_protocol_freezes_budgeted_experiment() -> None:
    protocol = load_budgeted_context_experiment_protocol(_PROTOCOL_PATH)

    assert protocol.protocol_id == "context-editing-budget-real-model-pilot-v4"
    assert protocol.status == "pre_registered_preflight_not_run"
    assert protocol.model.name == "qwen3.7-flash-2026-07-15"
    assert protocol.cases == (
        "large_search_context_repair",
        "large_search_context_recall",
    )
    assert protocol.baseline_configuration.to_payload() == {
        "configuration_schema_version": 2,
        "strategy": "identity",
        "max_inline_tool_result_bytes": None,
        "minimum_net_savings_bytes": None,
        "retrieval_tool_loading": None,
    }
    assert protocol.projection_configuration.to_payload() == {
        "configuration_schema_version": 3,
        "strategy": "budgeted_tool_result_reference",
        "max_request_bytes": 10_000,
        "protected_recent_batch_count": 2,
        "minimum_net_savings_bytes": 1,
        "excluded_tool_names": ["git_diff", "run_tests"],
        "max_retrievable_output_bytes": 50_000,
        "retrieval_tool_loading": "on_reference",
    }
    assert protocol.preflight_plan.case_id == "large_search_context_recall"
    assert protocol.preflight_plan.arm_order == ("baseline", "projection")
    assert protocol.preflight_plan.budget.maximum_runs == 2
    assert protocol.formal_budget.maximum_runs == 12
    assert protocol.advancement_gates.required_safe_task_successes_per_arm == 6

    cases_root = _PROJECT_ROOT / "benchmarks" / "coding_agent" / "cases"

    for case_id in protocol.cases:
        case_root = cases_root / case_id
        assert (case_root / "case.json").is_file()
        assert (case_root / "task.txt").is_file()
        assert (case_root / "acceptance.py").is_file()
        assert (case_root / "workspace").is_dir()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda payload: payload["arms"]["projection"].update(
                {"configuration_schema_version": 2}
            ),
            "unsupported budgeted context configuration schema 2",
        ),
        (
            lambda payload: payload["arms"]["baseline"].update(
                {"strategy": "tool_result_reference"}
            ),
            "baseline must be the complete schema-2 identity arm",
        ),
        (
            lambda payload: payload["preflight_budget"].update(
                {"maximum_runs": 3}
            ),
            "preflight run count must match arm order and budget",
        ),
    ),
)
def test_registered_v4_protocol_rejects_configuration_drift(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    payload = json.loads(_PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert callable(mutation)
    mutation(payload)
    mutated_path = tmp_path / "protocol.json"
    mutated_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_budgeted_context_experiment_protocol(mutated_path)
