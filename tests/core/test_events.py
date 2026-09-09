import pytest

from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.core.tool_calls import JsonValue


def test_event_kind_has_stable_values() -> None:
    assert tuple(EventKind) == (
        EventKind.RUN_STARTED,
        EventKind.RUN_RESUMED,
        EventKind.SKILL_SELECTION_FINISHED,
        EventKind.SKILL_LOAD_STARTED,
        EventKind.SKILL_LOAD_FINISHED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.TOOL_POLICY_DECIDED,
        EventKind.TOOL_APPROVAL_RESOLVED,
        EventKind.TOOL_EXECUTION_STARTED,
        EventKind.TOOL_EXECUTION_FINISHED,
        EventKind.CHECKPOINT_SAVED,
        EventKind.RUN_FINISHED,
    )


def test_ledger_event_preserves_audit_fact() -> None:
    event = LedgerEvent(
        run_id="run_001",
        sequence=1,
        kind=EventKind.RUN_STARTED,
        payload={
            "max_turns": 3,
            "max_tool_calls": 8,
        },
    )

    assert event.run_id == "run_001"
    assert event.sequence == 1
    assert event.kind is EventKind.RUN_STARTED
    assert event.payload == {
        "max_turns": 3,
        "max_tool_calls": 8,
    }


@pytest.mark.parametrize(
    (
        "run_id",
        "expected_error",
    ),
    [
        (
            None,
            TypeError,
        ),
        (
            17,
            TypeError,
        ),
        (
            "",
            ValueError,
        ),
        (
            " ",
            ValueError,
        ),
    ],
)
def test_ledger_event_rejects_invalid_run_id(
    run_id: object,
    expected_error: type[Exception],
) -> None:
    with pytest.raises(
        expected_error,
        match="run_id must",
    ):
        LedgerEvent(
            run_id=run_id,  # type: ignore[arg-type]
            sequence=1,
            kind=EventKind.RUN_STARTED,
            payload={},
        )


@pytest.mark.parametrize(
    (
        "sequence",
        "expected_error",
    ),
    [
        (
            None,
            TypeError,
        ),
        (
            "1",
            TypeError,
        ),
        (
            1.5,
            TypeError,
        ),
        (
            True,
            TypeError,
        ),
        (
            0,
            ValueError,
        ),
        (
            -1,
            ValueError,
        ),
    ],
)
def test_ledger_event_rejects_invalid_sequence(
    sequence: object,
    expected_error: type[Exception],
) -> None:
    with pytest.raises(
        expected_error,
        match="sequence must",
    ):
        LedgerEvent(
            run_id="run_001",
            sequence=sequence,  # type: ignore[arg-type]
            kind=EventKind.RUN_STARTED,
            payload={},
        )


@pytest.mark.parametrize(
    "kind",
    [
        "run_started",
        None,
        17,
    ],
)
def test_ledger_event_rejects_invalid_kind(
    kind: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="kind must be an EventKind",
    ):
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=kind,  # type: ignore[arg-type]
            payload={},
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "",
        None,
    ],
)
def test_ledger_event_rejects_invalid_payload(
    payload: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="payload must be a mapping",
    ):
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.RUN_STARTED,
            payload=payload,  # type: ignore[arg-type]
        )


def test_ledger_event_snapshots_payload() -> None:
    payload: dict[str, JsonValue] = {
        "tags": [
            "initial",
        ],
    }
    event = LedgerEvent(
        run_id="run_001",
        sequence=1,
        kind=EventKind.RUN_STARTED,
        payload=payload,
    )

    tags = payload["tags"]
    assert isinstance(tags, list)
    tags.append("changed")

    assert event.payload == {
        "tags": ("initial",),
    }

    with pytest.raises(TypeError):
        event.payload["new"] = "value"  # type: ignore[index]


def test_in_memory_event_ledger_assigns_order() -> None:
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )

    assert ledger.events == ()

    first_event = ledger.record(
        EventKind.RUN_STARTED,
        {
            "max_turns": 3,
        },
    )
    second_event = ledger.record(
        EventKind.MODEL_CALL_STARTED,
        {
            "turn": 1,
        },
    )

    assert first_event == LedgerEvent(
        run_id="run_001",
        sequence=1,
        kind=EventKind.RUN_STARTED,
        payload={
            "max_turns": 3,
        },
    )
    assert second_event == LedgerEvent(
        run_id="run_001",
        sequence=2,
        kind=EventKind.MODEL_CALL_STARTED,
        payload={
            "turn": 1,
        },
    )
    assert ledger.events == (
        first_event,
        second_event,
    )
