"""Shared context metrics derived from MiniCode Trace events."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from minicode.core.events import EventKind, LedgerEvent


@dataclass(frozen=True, slots=True)
class ContextTraceMetrics:
    """Context projection and readback facts shared by evaluators."""

    model_call_count: int
    model_visible_bytes: int
    canonical_bytes: int
    projection_bytes_saved: int
    changed_tool_result_count: int
    successful_readback_count: int
    failed_readback_count: int
    cancelled_readback_count: int


def summarize_context_trace(
    events: Sequence[LedgerEvent],
) -> ContextTraceMetrics:
    """Aggregate and cross-check shared context facts from Trace events."""
    model_call_count = 0
    model_visible_bytes = 0
    canonical_bytes = 0
    projection_bytes_saved = 0
    changed_tool_result_count = 0
    readback_outcomes = {
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }

    for event in events:
        if event.kind is EventKind.MODEL_CALL_STARTED:
            context_profile = _required_mapping(event.payload, "context_profile")
            projection = _required_mapping(event.payload, "context_projection")
            visible_bytes = _required_integer(context_profile, "total_bytes")
            before_bytes = _required_integer(projection, "total_bytes_before")
            after_bytes = _required_integer(projection, "total_bytes_after")
            saved_bytes = _required_integer(projection, "total_bytes_saved")

            if visible_bytes != after_bytes:
                raise ValueError("model-visible bytes disagree with projection Trace")

            if before_bytes - after_bytes != saved_bytes:
                raise ValueError("projection byte difference is inconsistent")

            model_call_count += 1
            model_visible_bytes += visible_bytes
            canonical_bytes += before_bytes
            projection_bytes_saved += saved_bytes
            changed_tool_result_count += _required_integer(
                projection,
                "changed_tool_result_count",
            )

        if (
            event.kind is EventKind.TOOL_EXECUTION_FINISHED
            and event.payload.get("tool_name") == "read_tool_result"
        ):
            outcome = event.payload.get("outcome")

            if not isinstance(outcome, str) or outcome not in readback_outcomes:
                raise ValueError("historical readback has an unknown outcome")

            readback_outcomes[outcome] += 1

    return ContextTraceMetrics(
        model_call_count=model_call_count,
        model_visible_bytes=model_visible_bytes,
        canonical_bytes=canonical_bytes,
        projection_bytes_saved=projection_bytes_saved,
        changed_tool_result_count=changed_tool_result_count,
        successful_readback_count=readback_outcomes["succeeded"],
        failed_readback_count=readback_outcomes["failed"],
        cancelled_readback_count=readback_outcomes["cancelled"],
    )


def _required_mapping(
    source: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = source.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")

    return value


def _required_integer(
    source: Mapping[str, object],
    key: str,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer")

    return value
