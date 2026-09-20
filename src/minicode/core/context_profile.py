"""Provider-neutral measurements for one model request."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from minicode.core.messages import Message
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolCall, ToolResult, to_plain_json
from minicode.tools.spec import ToolSpec


@dataclass(frozen=True, slots=True)
class ContextProfile:
    """Describe where a model request spends its context bytes."""

    instruction_bytes: int
    message_bytes: int
    tool_definition_bytes: int
    tool_call_bytes: int
    tool_result_bytes: int

    @property
    def total_bytes(self) -> int:
        """Return the sum of all measured context categories."""
        return (
            self.instruction_bytes
            + self.message_bytes
            + self.tool_definition_bytes
            + self.tool_call_bytes
            + self.tool_result_bytes
        )

    def to_payload(self) -> dict[str, int]:
        """Return a JSON-compatible event payload."""
        return {
            "instruction_bytes": self.instruction_bytes,
            "message_bytes": self.message_bytes,
            "tool_definition_bytes": self.tool_definition_bytes,
            "tool_call_bytes": self.tool_call_bytes,
            "tool_result_bytes": self.tool_result_bytes,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True, slots=True)
class ContextProjectionProfile:
    """Compare canonical context with the model-visible projection."""

    changed_tool_result_count: int
    tool_result_bytes_before: int
    tool_result_bytes_after: int
    total_bytes_before: int
    total_bytes_after: int

    @property
    def tool_result_bytes_saved(self) -> int:
        """Return tool-result bytes removed by projection."""
        return self.tool_result_bytes_before - self.tool_result_bytes_after

    @property
    def total_bytes_saved(self) -> int:
        """Return total request bytes removed by projection."""
        return self.total_bytes_before - self.total_bytes_after

    def to_payload(self) -> dict[str, int]:
        """Return a JSON-compatible event payload."""
        return {
            "changed_tool_result_count": self.changed_tool_result_count,
            "tool_result_bytes_before": self.tool_result_bytes_before,
            "tool_result_bytes_after": self.tool_result_bytes_after,
            "tool_result_bytes_saved": self.tool_result_bytes_saved,
            "total_bytes_before": self.total_bytes_before,
            "total_bytes_after": self.total_bytes_after,
            "total_bytes_saved": self.total_bytes_saved,
        }


def profile_model_request(request: ModelRequest) -> ContextProfile:
    """Measure semantic request components using canonical UTF-8 JSON."""
    messages: list[object] = []
    tool_calls: list[object] = []
    tool_results: list[object] = []

    for item in request.conversation:
        if isinstance(item, Message):
            messages.append(
                {
                    "role": item.role.value,
                    "content": item.content,
                }
            )
        elif isinstance(item, ToolCall):
            tool_calls.append(_tool_call_document(item))
        elif isinstance(item, ToolResult):
            tool_results.append(
                {
                    "call_id": item.call_id,
                    "output": item.output,
                    "is_error": item.is_error,
                }
            )

    return ContextProfile(
        instruction_bytes=_sequence_bytes(request.instructions),
        message_bytes=_sequence_bytes(messages),
        tool_definition_bytes=_sequence_bytes(
            [_tool_spec_document(spec) for spec in request.tool_specs]
        ),
        tool_call_bytes=_sequence_bytes(tool_calls),
        tool_result_bytes=_sequence_bytes(tool_results),
    )


def profile_context_projection(
    canonical_request: ModelRequest,
    projected_request: ModelRequest,
) -> ContextProjectionProfile:
    """Measure the observable effect of one context projection."""
    canonical_profile = profile_model_request(canonical_request)
    projected_profile = profile_model_request(projected_request)
    projected_results = {
        item.call_id: item
        for item in projected_request.conversation
        if isinstance(item, ToolResult)
    }
    changed_tool_result_count = sum(
        projected_results.get(item.call_id) != item
        for item in canonical_request.conversation
        if isinstance(item, ToolResult)
    )

    return ContextProjectionProfile(
        changed_tool_result_count=changed_tool_result_count,
        tool_result_bytes_before=canonical_profile.tool_result_bytes,
        tool_result_bytes_after=projected_profile.tool_result_bytes,
        total_bytes_before=canonical_profile.total_bytes,
        total_bytes_after=projected_profile.total_bytes,
    )


def _tool_call_document(tool_call: ToolCall) -> dict[str, object]:
    """Return the provider-neutral fields carried by one tool call."""
    return {
        "call_id": tool_call.call_id,
        "name": tool_call.name,
        "arguments": to_plain_json(tool_call.arguments),
    }


def _tool_spec_document(tool_spec: ToolSpec) -> dict[str, object]:
    """Return the model-visible definition of one tool."""
    return {
        "name": tool_spec.name,
        "description": tool_spec.description,
        "parameters": tool_spec.arguments_type.model_json_schema(),
    }


def _sequence_bytes(values: Sequence[object]) -> int:
    """Measure a non-empty sequence without charging empty categories."""
    if not values:
        return 0

    encoded = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(encoded)
