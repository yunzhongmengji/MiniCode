import json

import pytest

from minicode.context_comparison import (
    ContextComparisonScenario,
    run_offline_context_comparison,
    run_offline_context_comparison_suite,
)


@pytest.mark.asyncio
async def test_offline_context_comparison_is_reproducible_and_honest() -> None:
    first_report = await run_offline_context_comparison()
    second_report = await run_offline_context_comparison()

    assert first_report == second_report
    assert first_report.final_answer_matches is True
    assert first_report.both_runs_completed is True
    assert first_report.checkpoints_match_run_histories is True

    baseline = first_report.baseline
    projected = first_report.projected
    assert baseline.model_call_count == 3
    assert baseline.projection_bytes_saved == 0
    assert baseline.changed_tool_result_count == 0
    assert baseline.successful_readback_count == 0
    assert projected.model_call_count == 4
    assert projected.projection_bytes_saved > 0
    assert projected.changed_tool_result_count == 2
    assert projected.successful_readback_count == 1
    assert projected.model_visible_bytes > baseline.model_visible_bytes
    assert first_report.model_visible_byte_difference < 0
    assert first_report.cost_breakdown.equation_holds is True
    assert first_report.cost_breakdown.run_shape_overhead_bytes == 17087

    encoded = json.dumps(first_report.to_payload(), sort_keys=True)
    assert "canonical_json_utf8_bytes_not_model_tokens" in encoded
    assert '"projected_used_fewer_model_visible_bytes": false' in encoded


@pytest.mark.asyncio
async def test_no_readback_scenario_has_net_context_savings() -> None:
    first_report = await run_offline_context_comparison(
        ContextComparisonScenario.NO_HISTORICAL_READBACK
    )
    second_report = await run_offline_context_comparison(
        ContextComparisonScenario.NO_HISTORICAL_READBACK
    )

    assert first_report == second_report
    assert first_report.scenario is ContextComparisonScenario.NO_HISTORICAL_READBACK
    assert first_report.final_answer_matches is True
    assert first_report.both_runs_completed is True
    assert first_report.checkpoints_match_run_histories is True

    baseline = first_report.baseline
    projected = first_report.projected
    assert baseline.model_call_count == projected.model_call_count == 3
    assert baseline.tool_execution_count == projected.tool_execution_count == 2
    assert baseline.projection_bytes_saved == 0
    assert projected.projection_bytes_saved > 0
    assert projected.changed_tool_result_count == 1
    assert projected.successful_readback_count == 0
    assert projected.failed_readback_count == 0
    assert projected.cancelled_readback_count == 0
    assert projected.model_visible_bytes < baseline.model_visible_bytes
    assert first_report.model_visible_byte_difference > 0
    assert first_report.cost_breakdown.equation_holds is True
    assert first_report.cost_breakdown.run_shape_overhead_bytes == 1500

    encoded = json.dumps(first_report.to_payload(), sort_keys=True)
    assert '"scenario": "no_historical_readback"' in encoded
    assert '"projected_used_fewer_model_visible_bytes": true' in encoded


@pytest.mark.asyncio
async def test_context_comparison_suite_reports_illustrative_break_even() -> None:
    suite = await run_offline_context_comparison_suite()

    assert suite.break_even_eager_task_share_numerator == 3571
    assert suite.break_even_eager_task_share_denominator == 10516
    assert suite.break_even_eager_task_share_basis_points == 3396

    payload = suite.to_payload()
    break_even = payload["illustrative_break_even"]
    assert isinstance(break_even, dict)
    assert break_even["assumption"] == (
        "linear_mix_of_these_two_deterministic_endpoints"
    )
    assert break_even["is_production_threshold"] is False
