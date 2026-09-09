"""Dispatch tool calls to registered executable tools."""

import asyncio
from collections.abc import Mapping

from pydantic import ValidationError

from minicode.core.artifacts import ArtifactStore
from minicode.core.events import (
    EventKind,
    EventLedger,
)
from minicode.core.tool_approval import ToolApprover
from minicode.core.tool_calls import (
    JsonValue,
    ToolCall,
    ToolResult,
)
from minicode.core.tool_policy import (
    PolicyDecision,
    PolicyOutcome,
    ToolPolicy,
)
from minicode.tools.base import ToolExecutionError
from minicode.tools.registry import ToolRegistry


class ToolDispatcher:
    """Validate and execute tool calls through a registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        policy: ToolPolicy,
        approver: ToolApprover | None = None,
        event_ledger: EventLedger | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._approver = approver
        self._event_ledger = event_ledger
        self._artifact_store = artifact_store

    def _record_event(
        self,
        kind: EventKind,
        payload: Mapping[str, JsonValue],
    ) -> None:
        """Record an event when a ledger is configured."""
        if self._event_ledger is None:
            return

        self._event_ledger.record(
            kind,
            payload,
        )

    async def execute(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:
        """Execute a tool call or return a correlated error result."""
        tool = self._registry.get(tool_call.name)

        if tool is None:
            return ToolResult(
                call_id=tool_call.call_id,
                output=f"unknown tool: {tool_call.name}",
                is_error=True,
            )

        raw_arguments = dict(tool_call.arguments)

        try:
            validated_arguments = tool.spec.arguments_type.model_validate(raw_arguments)
        except ValidationError as error:
            validation_details = error.errors(
                include_url=False,
                include_input=False,
            )
            return ToolResult(
                call_id=tool_call.call_id,
                output=(
                    f"invalid arguments for tool "
                    f"'{tool_call.name}': {validation_details}"
                ),
                is_error=True,
            )

        decision = self._policy.evaluate(tool_call)

        if not isinstance(
            decision,
            PolicyDecision,
        ):
            raise TypeError("policy must return a PolicyDecision")

        self._record_event(
            EventKind.TOOL_POLICY_DECIDED,
            {
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
                "outcome": decision.outcome.value,
                "reason": decision.reason,
            },
        )

        if decision.outcome is PolicyOutcome.DENY:
            return ToolResult(
                call_id=tool_call.call_id,
                output=(f"tool '{tool_call.name}' denied by policy"),
                is_error=True,
            )

        if decision.outcome is PolicyOutcome.ASK:
            if self._approver is None:
                return ToolResult(
                    call_id=tool_call.call_id,
                    output=(f"tool '{tool_call.name}' requires approval"),
                    is_error=True,
                )

            approved = await self._approver.request_approval(
                tool_call,
                reason=decision.reason,
            )

            if not isinstance(approved, bool):
                raise TypeError("approver must return a boolean")

            self._record_event(
                EventKind.TOOL_APPROVAL_RESOLVED,
                {
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "approved": approved,
                },
            )

            if not approved:
                return ToolResult(
                    call_id=tool_call.call_id,
                    output=(f"tool '{tool_call.name}' approval denied"),
                    is_error=True,
                )

        self._record_event(
            EventKind.TOOL_EXECUTION_STARTED,
            {
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
            },
        )

        try:
            output = await tool.execute(validated_arguments)
        except asyncio.CancelledError:
            self._record_event(
                EventKind.TOOL_EXECUTION_FINISHED,
                {
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "outcome": "cancelled",
                },
            )
            raise
        except ToolExecutionError as error:
            failure_output = f"tool '{tool_call.name}' failed: {error}"
            failed_execution_payload: dict[
                str,
                JsonValue,
            ] = {
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
                "outcome": "failed",
                "error_type": type(error).__name__,
            }

            if self._artifact_store is not None:
                output_reference = self._artifact_store.put_text(
                    failure_output,
                    media_type="text/plain",
                )
                failed_execution_payload["output_artifact"] = {
                    "artifact_id": (output_reference.artifact_id),
                    "media_type": (output_reference.media_type),
                    "byte_count": (output_reference.byte_count),
                }

            self._record_event(
                EventKind.TOOL_EXECUTION_FINISHED,
                failed_execution_payload,
            )
            return ToolResult(
                call_id=tool_call.call_id,
                output=failure_output,
                is_error=True,
            )
        except Exception as error:
            self._record_event(
                EventKind.TOOL_EXECUTION_FINISHED,
                {
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "outcome": "failed",
                    "error_type": type(error).__name__,
                },
            )
            raise

        succeeded_execution_payload: dict[
            str,
            JsonValue,
        ] = {
            "call_id": tool_call.call_id,
            "tool_name": tool_call.name,
            "outcome": "succeeded",
        }

        if self._artifact_store is not None:
            output_reference = self._artifact_store.put_text(
                output,
                media_type="text/plain",
            )
            succeeded_execution_payload["output_artifact"] = {
                "artifact_id": (output_reference.artifact_id),
                "media_type": (output_reference.media_type),
                "byte_count": (output_reference.byte_count),
            }

        self._record_event(
            EventKind.TOOL_EXECUTION_FINISHED,
            succeeded_execution_payload,
        )

        return ToolResult(
            call_id=tool_call.call_id,
            output=output,
            is_error=False,
        )
