"""Projection boundary between canonical state and model-visible context."""

from collections.abc import Collection
from typing import Protocol

from minicode.core.context_editing import (
    apply_context_editing_plan,
    plan_context_editing,
)
from minicode.core.context_profile import profile_context_projection
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
    ContextProjectionConfiguration,
    ContextProjectionStrategy,
    RetrievalToolLoading,
    normalize_excluded_tool_names,
)
from minicode.core.context_retention import plan_tool_result_retention
from minicode.core.context_retrieval import (
    DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
    render_tool_result_reference,
)
from minicode.core.conversation import ConversationItem
from minicode.core.model import ModelRequest
from minicode.core.tool_calls import ToolResult
from minicode.tools.spec import ToolSpec


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


class BudgetedToolResultProjector:
    """Apply the pure editing plan behind an experimental projection boundary."""

    def __init__(
        self,
        *,
        max_request_bytes: int,
        retrieval_tool_spec: ToolSpec,
        protected_recent_batch_count: int = 1,
        excluded_tool_names: Collection[str] = frozenset(),
        max_retrievable_output_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
        minimum_net_savings_bytes: int = 1,
    ) -> None:
        if not isinstance(retrieval_tool_spec, ToolSpec):
            raise TypeError("retrieval_tool_spec must be a ToolSpec")

        if retrieval_tool_spec.name != "read_tool_result":
            raise ValueError("retrieval_tool_spec must describe read_tool_result")

        self._configuration = BudgetedContextProjectionConfiguration(
            max_request_bytes=max_request_bytes,
            protected_recent_batch_count=protected_recent_batch_count,
            minimum_net_savings_bytes=minimum_net_savings_bytes,
            excluded_tool_names=normalize_excluded_tool_names(excluded_tool_names),
            max_retrievable_output_bytes=max_retrievable_output_bytes,
        )
        self._retrieval_tool_spec = retrieval_tool_spec

    @property
    def configuration(self) -> BudgetedContextProjectionConfiguration:
        """Return the complete experimental configuration contract."""
        return self._configuration

    async def project(self, request: ModelRequest) -> ModelRequest:
        """Plan and materialize one budget-driven model-visible request."""
        configuration = self._configuration
        plan = plan_context_editing(
            request,
            max_request_bytes=configuration.max_request_bytes,
            retrieval_tool_spec=self._retrieval_tool_spec,
            protected_recent_batch_count=(
                configuration.protected_recent_batch_count
            ),
            excluded_tool_names=configuration.excluded_tool_names,
            max_retrievable_output_bytes=(
                configuration.max_retrievable_output_bytes
            ),
            minimum_net_savings_bytes=configuration.minimum_net_savings_bytes,
        )
        return apply_context_editing_plan(
            request,
            plan,
            retrieval_tool_spec=self._retrieval_tool_spec,
        )


class ToolResultReferenceProjector:
    """Replace eligible oversized tool outputs with retrievable references."""

    def __init__(
        self,
        *,
        max_inline_output_bytes: int,
        retrieval_tool_spec: ToolSpec,
        protected_recent_tool_result_batches: int = 1,
        max_retrievable_output_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
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

        if isinstance(protected_recent_tool_result_batches, bool) or not isinstance(
            protected_recent_tool_result_batches, int
        ):
            raise TypeError("protected_recent_tool_result_batches must be an integer")

        if protected_recent_tool_result_batches <= 0:
            raise ValueError(
                "protected_recent_tool_result_batches must be greater than zero"
            )

        if isinstance(max_retrievable_output_bytes, bool) or not isinstance(
            max_retrievable_output_bytes, int
        ):
            raise TypeError("max_retrievable_output_bytes must be an integer")

        if max_retrievable_output_bytes <= 0:
            raise ValueError("max_retrievable_output_bytes must be greater than zero")

        self._max_inline_output_bytes = max_inline_output_bytes
        self._retrieval_tool_spec = retrieval_tool_spec
        self._protected_recent_tool_result_batches = (
            protected_recent_tool_result_batches
        )
        self._max_retrievable_output_bytes = max_retrievable_output_bytes

    @property
    def max_inline_output_bytes(self) -> int:
        """Return the host-controlled inline output threshold."""
        return self._max_inline_output_bytes

    @property
    def minimum_net_savings_bytes(self) -> int:
        """Return the smallest complete-request saving that enables projection."""
        return 1

    @property
    def retrieval_tool_loading(self) -> RetrievalToolLoading:
        """Return when the historical-result retrieval tool becomes visible."""
        return RetrievalToolLoading.ON_REFERENCE

    @property
    def protected_recent_tool_result_batches(self) -> int:
        """Return how many newest result batches remain complete."""
        return self._protected_recent_tool_result_batches

    @property
    def max_retrievable_output_bytes(self) -> int:
        """Return the largest result that may safely become a reference."""
        return self._max_retrievable_output_bytes

    async def project(self, request: ModelRequest) -> ModelRequest:
        """Reference results only when the complete request becomes smaller."""
        retention = plan_tool_result_retention(
            request.conversation,
            protected_recent_batch_count=(self._protected_recent_tool_result_batches),
            max_retrievable_output_bytes=self._max_retrievable_output_bytes,
        )
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

            reference = render_tool_result_reference(
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

        if projection.total_bytes_saved < self.minimum_net_savings_bytes:
            return request

        return projected_request


def describe_context_projector(
    projector: ModelContextProjector,
) -> ContextProjectionConfiguration | BudgetedContextProjectionConfiguration:
    """Return stable trace metadata for a context projector."""
    if isinstance(projector, IdentityModelContextProjector):
        return ContextProjectionConfiguration(
            strategy=ContextProjectionStrategy.IDENTITY,
            max_inline_tool_result_bytes=None,
            minimum_net_savings_bytes=None,
            retrieval_tool_loading=None,
        )

    if isinstance(projector, BudgetedToolResultProjector):
        return projector.configuration

    if isinstance(projector, ToolResultReferenceProjector):
        if projector.protected_recent_tool_result_batches != 1:
            raise ValueError(
                "non-default tool-result retention is experimental and cannot "
                "enter the traced QueryLoop"
            )

        if (
            projector.max_retrievable_output_bytes
            != DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES
        ):
            raise ValueError(
                "non-default tool-result retrieval capacity is experimental and "
                "cannot enter the traced QueryLoop"
            )

        return ContextProjectionConfiguration(
            strategy=ContextProjectionStrategy.TOOL_RESULT_REFERENCE,
            max_inline_tool_result_bytes=projector.max_inline_output_bytes,
            minimum_net_savings_bytes=projector.minimum_net_savings_bytes,
            retrieval_tool_loading=projector.retrieval_tool_loading,
        )

    return ContextProjectionConfiguration(
        strategy=ContextProjectionStrategy.CUSTOM,
        max_inline_tool_result_bytes=None,
        minimum_net_savings_bytes=None,
        retrieval_tool_loading=None,
    )
