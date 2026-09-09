"""Static contracts for events, checkpoints, and replay."""

from minicode.core.checkpoints import (
    CheckpointStore,
    InMemoryCheckpointStore,
    RunCheckpoint,
)
from minicode.core.events import (
    EventKind,
    EventLedger,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.core.replay import RunReplay


def build_event_ledger_as_protocol() -> EventLedger:
    """Require the in-memory ledger to satisfy EventLedger."""
    return InMemoryEventLedger(
        run_id="run_001",
    )


def record_started_event(
    ledger: EventLedger,
) -> LedgerEvent:
    """Require EventLedger to accept and return typed events."""
    return ledger.record(
        EventKind.RUN_STARTED,
        {
            "initial_history_items": 1,
        },
    )


def build_checkpoint_store_as_protocol() -> CheckpointStore:
    """Require the in-memory store to satisfy CheckpointStore."""
    return InMemoryCheckpointStore()


def save_and_load_checkpoint(
    store: CheckpointStore,
) -> RunCheckpoint | None:
    """Require checkpoint storage methods to agree on types."""
    checkpoint = RunCheckpoint(
        run_id="run_001",
        message_history=(),
        turns_used=0,
        tool_calls_used=0,
    )

    store.save(checkpoint)

    return store.latest("run_001")


def summarize_replay(
    replay: RunReplay,
) -> tuple[
    str,
    bool,
    str | None,
    int,
    int,
    int,
]:
    """Require replay summary properties to remain stable."""
    return (
        replay.run_id,
        replay.is_finished,
        replay.outcome,
        replay.model_call_count,
        replay.tool_execution_count,
        replay.checkpoint_count,
    )
