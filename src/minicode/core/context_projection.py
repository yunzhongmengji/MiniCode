"""Projection boundary between canonical state and model-visible context."""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from minicode.core.context_profile import profile_context_projection
from minicode.core.context_retention import plan_tool_result_retention
from minicode.core.conversation import ConversationItem
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolResult
from minicode.tools.spec import ToolSpec


class ContextProjectionStrategy(StrEnum):
    """Stable names for model-context projection behavior."""

    IDENTITY = "identity"
    TOOL_RESULT_REFERENCE = "tool_result_reference"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ContextProjectionConfiguration:
    """Trace-visible configuration of one context projector."""

    strategy: ContextProjectionStrategy
    max_inline_tool_result_bytes: int | None

    def to_payload(self) -> dict[str, str | int | None]:
        """Return a JSON-compatible configuration document."""
        return {
            "strategy": self.strategy,
            "max_inline_tool_result_bytes": self.max_inline_tool_result_bytes,
        }


class ModelContextProjector(Protocol):
    """Build the model-visible view of one canonical request."""

    async def project(self, request: ModelRequest) -> ModelRequest:
        """Return the request that should be sent to the model."""
        ...


class IdentityModelContextProjector:
    """Preserve the complete request without compression."""

    async def project(self, request: ModelRequest) -> ModelRequest:
        """Return the canonical request unchanged."""
        return request


class ToolResultReferenceProjector:
    """Replace eligible oversized tool outputs with retrievable references."""

    def __init__(
        self,
        *,
        max_inline_output_bytes: int,
        retrieval_tool_spec: ToolSpec,
    ) -> None:
        if isinstance(max_inline_output_bytes, bool) or not isinstance(
            max_inline_output_bytes,
            int,
        ):
            raise TypeError("max_inline_output_bytes must be an integer")

        if max_inline_output_bytes < 0:
            raise ValueError("max_inline_output_bytes must not be negative")

        if not isinstance(retrieval_tool_spec, ToolSpec):
            raise TypeError("retrieval_tool_spec must be a ToolSpec")

        if retrieval_tool_spec.name != "read_tool_result":
            raise ValueError("retrieval_tool_spec must describe read_tool_result")

        self._max_inline_output_bytes = max_inline_output_bytes
        self._retrieval_tool_spec = retrieval_tool_spec

    @property
    def max_inline_output_bytes(self) -> int:
        """Return the host-controlled inline output threshold."""
        return self._max_inline_output_bytes

    async def project(self, request: ModelRequest) -> ModelRequest:
        """Reference results only when the complete request becomes smaller."""
        retention = plan_tool_result_retention(request.conversation)
        eligible_call_ids = frozenset(retention.eligible_call_ids)
        projected_conversation: list[ConversationItem] = []
        changed = False

        for item in request.conversation:
            if not isinstance(item, ToolResult):
                projected_conversation.append(item)
                continue

            original_bytes = len(item.output.encode("utf-8"))

            if (
                item.call_id not in eligible_call_ids
                or original_bytes <= self._max_inline_output_bytes
            ):
                projected_conversation.append(item)
                continue

            reference = _render_tool_result_reference(
                call_id=item.call_id,
                original_output_bytes=original_bytes,
            )

            if len(reference.encode("utf-8")) >= original_bytes:
                projected_conversation.append(item)
                continue

            projected_conversation.append(
                ToolResult(
                    call_id=item.call_id,
                    output=reference,
                    is_error=item.is_error,
                )
            )
            changed = True

        if not changed:
            return request

        projected_request = ModelRequest(
            conversation=projected_conversation,
            tool_specs=(*request.tool_specs, self._retrieval_tool_spec),
            instructions=request.instructions,
        )

        projection = profile_context_projection(request, projected_request)

        if projection.total_bytes_saved <= 0:
            return request

        return projected_request


def describe_context_projector(
    projector: ModelContextProjector,
) -> ContextProjectionConfiguration:
    """Return stable trace metadata for a context projector."""
    if isinstance(projector, IdentityModelContextProjector):
        return ContextProjectionConfiguration(
            strategy=ContextProjectionStrategy.IDENTITY,
            max_inline_tool_result_bytes=None,
        )

    if isinstance(projector, ToolResultReferenceProjector):
        return ContextProjectionConfiguration(
            strategy=ContextProjectionStrategy.TOOL_RESULT_REFERENCE,
            max_inline_tool_result_bytes=projector.max_inline_output_bytes,
        )

    return ContextProjectionConfiguration(
        strategy=ContextProjectionStrategy.CUSTOM,
        max_inline_tool_result_bytes=None,
    )


def _render_tool_result_reference(
    *,
    call_id: str,
    original_output_bytes: int,
) -> str:
    """Render an unambiguous reference understood by the retrieval tool."""
    return json.dumps(
        {
            "call_id": call_id,
            "kind": "historical_tool_result_reference",
            "original_output_bytes": original_output_bytes,
            "retrieval_tool": "read_tool_result",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
