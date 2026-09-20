import pytest

from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)


def test_budgeted_configuration_round_trip_preserves_complete_contract() -> None:
    configuration = BudgetedContextProjectionConfiguration(
        max_request_bytes=120_000,
        protected_recent_batch_count=2,
        minimum_net_savings_bytes=512,
        excluded_tool_names=("run_tests", "git_diff"),
        max_retrievable_output_bytes=50_000,
    )

    payload = configuration.to_payload()
    decoded = BudgetedContextProjectionConfiguration.from_payload(payload)

    assert payload == {
        "configuration_schema_version": 3,
        "strategy": "budgeted_tool_result_reference",
        "max_request_bytes": 120_000,
        "protected_recent_batch_count": 2,
        "minimum_net_savings_bytes": 512,
        "excluded_tool_names": ["git_diff", "run_tests"],
        "max_retrievable_output_bytes": 50_000,
        "retrieval_tool_loading": "on_reference",
    }
    assert decoded == configuration


def test_budgeted_configuration_normalizes_excluded_tool_names() -> None:
    configuration = BudgetedContextProjectionConfiguration(
        max_request_bytes=1_000,
        protected_recent_batch_count=1,
        minimum_net_savings_bytes=1,
        excluded_tool_names=("run_tests", "git_diff", "run_tests"),
        max_retrievable_output_bytes=500,
    )

    assert configuration.excluded_tool_names == ("git_diff", "run_tests")


def test_budgeted_configuration_rejects_wrong_schema() -> None:
    payload: dict[str, object] = {
        "configuration_schema_version": 2,
        "strategy": "budgeted_tool_result_reference",
        "max_request_bytes": 1_000,
        "protected_recent_batch_count": 1,
        "minimum_net_savings_bytes": 1,
        "excluded_tool_names": [],
        "max_retrievable_output_bytes": 500,
        "retrieval_tool_loading": "on_reference",
    }

    with pytest.raises(
        ValueError,
        match="unsupported budgeted context configuration schema 2",
    ):
        BudgetedContextProjectionConfiguration.from_payload(payload)


def test_budgeted_configuration_rejects_missing_behavior_field() -> None:
    payload: dict[str, object] = {
        "configuration_schema_version": 3,
        "strategy": "budgeted_tool_result_reference",
        "max_request_bytes": 1_000,
        "protected_recent_batch_count": 1,
        "minimum_net_savings_bytes": 1,
        "excluded_tool_names": [],
        "retrieval_tool_loading": "on_reference",
    }

    with pytest.raises(
        ValueError,
        match="missing=\\['max_retrievable_output_bytes'\\]",
    ):
        BudgetedContextProjectionConfiguration.from_payload(payload)


def test_budgeted_configuration_rejects_unknown_loading_mode() -> None:
    with pytest.raises(ValueError, match="retrieval_tool_loading must be on_reference"):
        BudgetedContextProjectionConfiguration(
            max_request_bytes=1_000,
            protected_recent_batch_count=1,
            minimum_net_savings_bytes=1,
            excluded_tool_names=(),
            max_retrievable_output_bytes=500,
            retrieval_tool_loading="eager",  # type: ignore[arg-type]
        )
