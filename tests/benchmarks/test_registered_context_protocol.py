import json
from pathlib import Path

from minicode.evaluation_summary import _load_context_protocol

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROTOCOL_PATH = (
    _PROJECT_ROOT / "benchmarks" / "context_projection" / "real_model_protocol_v3.json"
)


def test_registered_v3_protocol_matches_recall_experiment() -> None:
    protocol = _load_context_protocol(_PROTOCOL_PATH)
    payload = json.loads(_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert protocol.protocol_id == (
        "context-projection-evidence-recall-real-model-pilot-v3"
    )
    assert protocol.cases == (
        "large_search_context_repair",
        "large_search_context_recall",
    )
    assert protocol.baseline_threshold is None
    assert protocol.projection_threshold == 500
    assert protocol.repetitions_per_case_per_arm == 3
    assert protocol.required_safe_task_successes_per_arm == 6
    assert protocol.preflight_plan is not None
    assert protocol.preflight_plan.case_id == "large_search_context_recall"
    assert protocol.preflight_plan.arm_order == ("baseline", "projection")
    assert protocol.preflight_plan.maximum_runs == 2
    assert protocol.preflight_plan.maximum_input_tokens == 45_000
    assert protocol.preflight_plan.maximum_output_tokens == 5_000

    assert payload["status"] == "pre_registered_preflight_not_run"
    assert payload["formal_budget"] == {
        "maximum_runs": 12,
        "maximum_input_tokens": 270_000,
        "maximum_output_tokens": 30_000,
    }

    cases_root = _PROJECT_ROOT / "benchmarks" / "coding_agent" / "cases"

    for case_id in protocol.cases:
        case_root = cases_root / case_id
        assert (case_root / "case.json").is_file()
        assert (case_root / "task.txt").is_file()
        assert (case_root / "acceptance.py").is_file()
        assert (case_root / "workspace").is_dir()
