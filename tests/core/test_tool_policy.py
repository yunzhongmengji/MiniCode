import pytest

from minicode.core.tool_calls import ToolCall
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)


def test_policy_outcome_has_three_stable_values() -> None:
    assert PolicyOutcome.ALLOW.value == "allow"
    assert PolicyOutcome.ASK.value == "ask"
    assert PolicyOutcome.DENY.value == "deny"


def test_policy_decision_preserves_outcome_and_reason() -> None:
    decision = PolicyDecision(
        outcome=PolicyOutcome.ASK,
        reason="tool may modify workspace files",
    )

    assert decision.outcome is PolicyOutcome.ASK
    assert decision.reason == ("tool may modify workspace files")


@pytest.mark.parametrize(
    "outcome",
    [
        "allow",
        {},
        17,
    ],
)
def test_policy_decision_rejects_invalid_outcome(
    outcome: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="outcome must be a PolicyOutcome",
    ):
        PolicyDecision(
            outcome=outcome,  # type: ignore[arg-type]
            reason="test reason",
        )


@pytest.mark.parametrize(
    "reason",
    [
        None,
        17,
        b"reason",
    ],
)
def test_policy_decision_rejects_non_string_reason(
    reason: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="reason must be a string",
    ):
        PolicyDecision(
            outcome=PolicyOutcome.DENY,
            reason=reason,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "reason",
    [
        "",
        " ",
        "\t",
    ],
)
def test_policy_decision_rejects_blank_reason(
    reason: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="reason must not be blank",
    ):
        PolicyDecision(
            outcome=PolicyOutcome.DENY,
            reason=reason,
        )


def test_configured_tool_policy_uses_rules_and_denies_by_default() -> None:
    read_decision = PolicyDecision(
        outcome=PolicyOutcome.ALLOW,
        reason="workspace reads are allowed",
    )
    edit_decision = PolicyDecision(
        outcome=PolicyOutcome.ASK,
        reason="workspace writes require approval",
    )
    policy = ConfiguredToolPolicy(
        decisions={
            "read_file": read_decision,
            "edit_file": edit_decision,
        },
    )

    read_result = policy.evaluate(
        ToolCall(
            call_id="call_001",
            name="read_file",
            arguments={
                "path": "README.md",
            },
        )
    )
    edit_result = policy.evaluate(
        ToolCall(
            call_id="call_002",
            name="edit_file",
            arguments={
                "path": "README.md",
            },
        )
    )
    unknown_result = policy.evaluate(
        ToolCall(
            call_id="call_003",
            name="run_shell",
            arguments={},
        )
    )

    assert read_result == read_decision
    assert edit_result == edit_decision
    assert unknown_result == PolicyDecision(
        outcome=PolicyOutcome.DENY,
        reason="tool is not configured by policy",
    )


@pytest.mark.parametrize(
    "decisions",
    [
        [],
        "",
        b"",
    ],
)
def test_configured_tool_policy_rejects_invalid_container(
    decisions: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="decisions must be a mapping",
    ):
        ConfiguredToolPolicy(
            decisions=decisions,  # type: ignore[arg-type]
        )


def test_configured_tool_policy_rejects_invalid_entries() -> None:
    allow = PolicyDecision(
        outcome=PolicyOutcome.ALLOW,
        reason="allowed for test",
    )

    with pytest.raises(
        TypeError,
        match="policy tool names must be strings",
    ):
        ConfiguredToolPolicy(
            decisions={
                17: allow,
            },  # type: ignore[dict-item]
        )

    with pytest.raises(
        ValueError,
        match="policy tool names must not be blank",
    ):
        ConfiguredToolPolicy(
            decisions={
                " ": allow,
            },
        )

    with pytest.raises(
        TypeError,
        match="policy rules must be PolicyDecision instances",
    ):
        ConfiguredToolPolicy(
            decisions={
                "read_file": "allow",
            },  # type: ignore[dict-item]
        )


def test_configured_tool_policy_snapshots_rules() -> None:
    allow = PolicyDecision(
        outcome=PolicyOutcome.ALLOW,
        reason="workspace reads are allowed",
    )
    decisions = {
        "read_file": allow,
    }
    policy = ConfiguredToolPolicy(
        decisions=decisions,
    )

    decisions["run_shell"] = allow

    result = policy.evaluate(
        ToolCall(
            call_id="call_001",
            name="run_shell",
            arguments={},
        )
    )

    assert result == PolicyDecision(
        outcome=PolicyOutcome.DENY,
        reason="tool is not configured by policy",
    )
