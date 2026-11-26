"""Recoverable agent runtime with atomic checkpoints and approval suspension."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from minicode.context.manager import BudgetedContextManager
from minicode.context.read_artifact import (
    READ_ARTIFACT_TOOL_NAME,
    ReadArtifactTool,
    active_session_id_var,
)
from minicode.models.base import Model, ModelRequest
from minicode.runtime.policy import ToolRiskPolicy, build_default_risk_policy
from minicode.schemas.checkpoints import (
    ApprovalDecision,
    PendingApproval,
    SessionCheckpoint,
    SessionStatus,
)
from minicode.schemas.events import EventType, LedgerEventInput
from minicode.schemas.messages import (
    MessageRecord,
    MessageRole,
    ToolCallRecord,
    ToolResultRecord,
)
from minicode.storage.store import SqliteRuntimeStorage
from minicode.tools.base import ToolExecutionError
from minicode.tools.registry import ToolRegistry


class SessionNotFoundError(LookupError):
    """Raised when a requested session does not exist in storage."""


class InvalidSessionStateError(RuntimeError):
    """Raised when an operation is invalid for the session's current status."""


class ApprovalPendingError(InvalidSessionStateError):
    """Raised when resume is called while the session awaits explicit approval."""


class SessionRunResult(BaseModel):
    """Observable outcome of starting, resuming, or approving a session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    status: SessionStatus
    step: int = Field(ge=0)
    turns_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    final_answer: str | None = None
    pending_approval: PendingApproval | None = None

    @classmethod
    def from_checkpoint(cls, checkpoint: SessionCheckpoint) -> SessionRunResult:
        """Build a run result summary from the latest persisted checkpoint."""
        return cls(
            session_id=checkpoint.session_id,
            status=checkpoint.status,
            step=checkpoint.step,
            turns_used=checkpoint.turns_used,
            tool_calls_used=checkpoint.tool_calls_used,
            total_input_tokens=checkpoint.total_input_tokens,
            total_output_tokens=checkpoint.total_output_tokens,
            final_answer=checkpoint.final_answer,
            pending_approval=checkpoint.pending_approval,
        )


class RecoverableAgentRuntime:
    """Step-checkpointed agent runtime backed by SQLite transactions."""

    def __init__(
        self,
        *,
        model: Model,
        tool_registry: ToolRegistry,
        storage: SqliteRuntimeStorage,
        risk_policy: ToolRiskPolicy | None = None,
        context_manager: BudgetedContextManager | None = None,
        instructions: Sequence[str] = (),
        max_turns: int = 8,
        max_tool_calls: int = 16,
    ) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be greater than zero")
        if max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be greater than zero")

        self._model = model
        self._tool_registry = tool_registry
        self._storage = storage
        self._context_manager = context_manager
        self._builtin_read_artifact: ReadArtifactTool | None = (
            ReadArtifactTool(event_ledger=storage.event_ledger)
            if (
                context_manager is not None
                and tool_registry.get(READ_ARTIFACT_TOOL_NAME) is None
            )
            else None
        )
        self._tool_specs = (
            (*tool_registry.specs, self._builtin_read_artifact.spec)
            if self._builtin_read_artifact is not None
            else tool_registry.specs
        )
        self._risk_policy = (
            build_default_risk_policy() if risk_policy is None else risk_policy
        )
        self._instructions = tuple(instructions)
        self._max_turns = max_turns
        self._max_tool_calls = max_tool_calls

    async def start(
        self,
        task: str,
        *,
        session_id: str | None = None,
    ) -> SessionRunResult:
        """Start a new durable session and run until completion or pause."""
        if not task.strip():
            raise ValueError("task must not be blank")

        resolved_session_id = (
            f"sess_{uuid4().hex[:16]}" if session_id is None else session_id
        )
        if self._storage.checkpoint_store.load_latest(resolved_session_id) is not None:
            raise InvalidSessionStateError(
                f"session '{resolved_session_id}' already exists"
            )

        initial_checkpoint = SessionCheckpoint(
            session_id=resolved_session_id,
            step=0,
            status=SessionStatus.RUNNING,
            history=(MessageRecord(role=MessageRole.USER, content=task),),
        )
        self._storage.commit_step(
            checkpoint=initial_checkpoint,
            events=(
                LedgerEventInput(
                    event_type=EventType.SESSION_STARTED,
                    payload={
                        "task": task,
                        "max_turns": self._max_turns,
                        "max_tool_calls": self._max_tool_calls,
                    },
                ),
            ),
        )
        return await self._drive(initial_checkpoint)

    async def resume(self, session_id: str) -> SessionRunResult:
        """Resume an interrupted session from its latest persisted checkpoint."""
        checkpoint = self._require_checkpoint(session_id)

        if checkpoint.status is SessionStatus.WAITING_APPROVAL:
            assert checkpoint.pending_approval is not None
            raise ApprovalPendingError(
                f"session '{session_id}' is waiting approval for tool "
                f"'{checkpoint.pending_approval.tool_name}' "
                f"(call_id='{checkpoint.pending_approval.call_id}')"
            )

        if checkpoint.status in (SessionStatus.COMPLETED, SessionStatus.ABORTED):
            raise InvalidSessionStateError(
                f"cannot resume session '{session_id}' in terminal status "
                f"'{checkpoint.status.value}'"
            )

        resumed_checkpoint = checkpoint.model_copy(
            update={
                "step": checkpoint.step + 1,
                "status": SessionStatus.RUNNING,
            }
        )
        self._storage.commit_step(
            checkpoint=resumed_checkpoint,
            events=(
                LedgerEventInput(
                    event_type=EventType.SESSION_RESUMED,
                    payload={
                        "resumed_from_step": checkpoint.step,
                        "turns_used": checkpoint.turns_used,
                        "tool_calls_used": checkpoint.tool_calls_used,
                        "pending_tool_calls": len(checkpoint.pending_tool_calls),
                    },
                ),
            ),
        )
        return await self._drive(resumed_checkpoint)

    async def resolve_approval(
        self,
        session_id: str,
        decision: ApprovalDecision,
        *,
        reason: str = "",
        continue_run: bool = True,
    ) -> SessionRunResult:
        """Apply an external approve/reject decision to a paused session."""
        checkpoint = self._require_checkpoint(session_id)
        if (
            checkpoint.status is not SessionStatus.WAITING_APPROVAL
            or checkpoint.pending_approval is None
        ):
            raise InvalidSessionStateError(
                f"session '{session_id}' is not waiting for approval "
                f"(status='{checkpoint.status.value}')"
            )

        pending = checkpoint.pending_approval
        next_step = checkpoint.step + 1
        decision_event = LedgerEventInput(
            event_type=EventType.APPROVAL_DECIDED,
            payload={
                "call_id": pending.call_id,
                "tool_name": pending.tool_name,
                "risk_level": pending.risk_level.value,
                "decision": decision.value,
                "reason": reason,
            },
        )

        if decision is ApprovalDecision.REJECT:
            aborted_checkpoint = checkpoint.model_copy(
                update={
                    "step": next_step,
                    "status": SessionStatus.ABORTED,
                    "pending_approval": None,
                }
            )
            self._storage.commit_step(
                checkpoint=aborted_checkpoint,
                events=(
                    decision_event,
                    LedgerEventInput(
                        event_type=EventType.SESSION_ABORTED,
                        payload={
                            "reason": reason or "high-risk tool call rejected",
                            "rejected_call_id": pending.call_id,
                            "rejected_tool_name": pending.tool_name,
                        },
                    ),
                ),
            )
            return SessionRunResult.from_checkpoint(aborted_checkpoint)

        approved_ids = tuple(
            dict.fromkeys((*checkpoint.approved_call_ids, pending.call_id))
        )
        resumed_checkpoint = checkpoint.model_copy(
            update={
                "step": next_step,
                "status": SessionStatus.RUNNING,
                "pending_approval": None,
                "approved_call_ids": approved_ids,
            }
        )
        self._storage.commit_step(
            checkpoint=resumed_checkpoint,
            events=(decision_event,),
        )
        if not continue_run:
            return SessionRunResult.from_checkpoint(resumed_checkpoint)
        return await self._drive(resumed_checkpoint)

    async def approve(
        self,
        session_id: str,
        *,
        reason: str = "",
        continue_run: bool = True,
    ) -> SessionRunResult:
        """Approve the pending high-risk tool call and continue execution."""
        return await self.resolve_approval(
            session_id,
            ApprovalDecision.APPROVE,
            reason=reason,
            continue_run=continue_run,
        )

    async def reject(
        self,
        session_id: str,
        *,
        reason: str = "",
    ) -> SessionRunResult:
        """Reject the pending high-risk tool call and abort the session."""
        return await self.resolve_approval(
            session_id,
            ApprovalDecision.REJECT,
            reason=reason,
            continue_run=False,
        )

    def _require_checkpoint(self, session_id: str) -> SessionCheckpoint:
        checkpoint = self._storage.checkpoint_store.load_latest(session_id)
        if checkpoint is None:
            raise SessionNotFoundError(f"session '{session_id}' not found")
        return checkpoint

    async def _drive(self, checkpoint: SessionCheckpoint) -> SessionRunResult:
        token = active_session_id_var.set(checkpoint.session_id)
        try:
            current = checkpoint
            while True:
                current, paused = await self._drain_pending_tools(current)
                if paused is not None:
                    return paused

                current, finished = await self._run_reasoning_turn(current)
                if finished is not None:
                    return finished
        finally:
            active_session_id_var.reset(token)

    async def _drain_pending_tools(
        self,
        checkpoint: SessionCheckpoint,
    ) -> tuple[SessionCheckpoint, SessionRunResult | None]:
        """Execute pending tool calls one by one, pausing on unapproved high-risk tools."""
        current = checkpoint
        while current.pending_tool_calls:
            tool_call = current.pending_tool_calls[0]
            remaining = current.pending_tool_calls[1:]

            assessment = self._risk_policy.assess(tool_call.name)
            if (
                assessment.requires_approval
                and tool_call.call_id not in current.approved_call_ids
            ):
                pending = PendingApproval(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    risk_level=assessment.risk_level,
                    reason=assessment.reason,
                )
                paused_checkpoint = current.model_copy(
                    update={
                        "step": current.step + 1,
                        "status": SessionStatus.WAITING_APPROVAL,
                        "pending_approval": pending,
                    }
                )
                self._storage.commit_step(
                    checkpoint=paused_checkpoint,
                    events=(
                        LedgerEventInput(
                            event_type=EventType.APPROVAL_REQUIRED,
                            payload={
                                "call_id": pending.call_id,
                                "tool_name": pending.tool_name,
                                "arguments": pending.arguments,
                                "risk_level": pending.risk_level.value,
                                "reason": pending.reason,
                            },
                        ),
                        LedgerEventInput(
                            event_type=EventType.SESSION_PAUSED,
                            payload={
                                "status": SessionStatus.WAITING_APPROVAL.value,
                                "call_id": pending.call_id,
                                "tool_name": pending.tool_name,
                            },
                        ),
                    ),
                )
                return paused_checkpoint, SessionRunResult.from_checkpoint(
                    paused_checkpoint
                )

            tool_result = await self._execute_tool(tool_call)
            next_approved_ids = tuple(
                cid for cid in current.approved_call_ids if cid != tool_call.call_id
            )
            current = current.model_copy(
                update={
                    "step": current.step + 1,
                    "status": SessionStatus.RUNNING,
                    "history": (*current.history, tool_result),
                    "pending_tool_calls": remaining,
                    "approved_call_ids": next_approved_ids,
                    "tool_calls_used": current.tool_calls_used + 1,
                }
            )
            self._storage.commit_step(
                checkpoint=current,
                events=(
                    LedgerEventInput(
                        event_type=EventType.TOOL_EXECUTED,
                        payload={
                            "call_id": tool_call.call_id,
                            "tool_name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "output": tool_result.output,
                            "is_error": tool_result.is_error,
                        },
                    ),
                ),
            )
        return current, None

    async def _run_reasoning_turn(
        self,
        checkpoint: SessionCheckpoint,
    ) -> tuple[SessionCheckpoint, SessionRunResult | None]:
        """Project model-visible context, invoke the LLM, and atomically persist output."""
        if checkpoint.turns_used >= self._max_turns:
            aborted = checkpoint.model_copy(
                update={"step": checkpoint.step + 1, "status": SessionStatus.ABORTED}
            )
            self._storage.commit_step(
                checkpoint=aborted,
                events=(
                    LedgerEventInput(
                        event_type=EventType.SESSION_ABORTED,
                        payload={"reason": "max_turns_reached"},
                    ),
                ),
            )
            return aborted, SessionRunResult.from_checkpoint(aborted)

        context_metadata: dict[str, object] = {}
        if self._context_manager is not None:
            context_view = self._context_manager.build_view(
                session_id=checkpoint.session_id,
                full_history=checkpoint.history,
                instructions=self._instructions,
                tool_specs=self._tool_specs,
            )
            model_conversation = context_view.conversation
            context_metadata = {
                "original_context_tokens": context_view.original_tokens,
                "visible_context_tokens": context_view.estimated_tokens,
                "compressed_event_ids": [
                    ref.event_id for ref in context_view.compressed_refs
                ],
            }
        else:
            model_conversation = checkpoint.history

        request = ModelRequest(
            conversation=model_conversation,
            tool_specs=self._tool_specs,
            instructions=self._instructions,
        )
        response = await self._model.complete(request)
        token_usage = response.usage
        total_in = checkpoint.total_input_tokens + (
            token_usage.input_tokens if token_usage is not None else 0
        )
        total_out = checkpoint.total_output_tokens + (
            token_usage.output_tokens if token_usage is not None else 0
        )
        turns_used = checkpoint.turns_used + 1
        proposed_calls = response.tool_calls

        reasoning_event = LedgerEventInput(
            event_type=EventType.REASONING_COMPLETED,
            payload={
                "turn": turns_used,
                "thinking": response.content,
                "tool_calls": [
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in proposed_calls
                ],
                **context_metadata,
            },
            token_usage=token_usage,
        )

        if not proposed_calls:
            next_history = (
                (
                    *checkpoint.history,
                    MessageRecord(role=MessageRole.ASSISTANT, content=response.content),
                )
                if response.content.strip()
                else checkpoint.history
            )
            completed = checkpoint.model_copy(
                update={
                    "step": checkpoint.step + 1,
                    "status": SessionStatus.COMPLETED,
                    "history": next_history,
                    "turns_used": turns_used,
                    "total_input_tokens": total_in,
                    "total_output_tokens": total_out,
                    "final_answer": response.content,
                }
            )
            self._storage.commit_step(
                checkpoint=completed,
                events=(
                    reasoning_event,
                    LedgerEventInput(
                        event_type=EventType.SESSION_COMPLETED,
                        payload={
                            "final_answer": response.content,
                            "turns_used": turns_used,
                            "tool_calls_used": checkpoint.tool_calls_used,
                        },
                    ),
                ),
            )
            return completed, SessionRunResult.from_checkpoint(completed)

        if checkpoint.tool_calls_used + len(proposed_calls) > self._max_tool_calls:
            aborted = checkpoint.model_copy(
                update={
                    "step": checkpoint.step + 1,
                    "status": SessionStatus.ABORTED,
                    "turns_used": turns_used,
                    "total_input_tokens": total_in,
                    "total_output_tokens": total_out,
                }
            )
            self._storage.commit_step(
                checkpoint=aborted,
                events=(
                    reasoning_event,
                    LedgerEventInput(
                        event_type=EventType.SESSION_ABORTED,
                        payload={"reason": "max_tool_calls_exceeded"},
                    ),
                ),
            )
            return aborted, SessionRunResult.from_checkpoint(aborted)

        next_history = checkpoint.history
        if response.content.strip():
            next_history = (
                *next_history,
                MessageRecord(role=MessageRole.ASSISTANT, content=response.content),
            )
        next_history = (*next_history, *proposed_calls)

        reasoning_checkpoint = checkpoint.model_copy(
            update={
                "step": checkpoint.step + 1,
                "status": SessionStatus.RUNNING,
                "history": next_history,
                "pending_tool_calls": proposed_calls,
                "turns_used": turns_used,
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
            }
        )
        self._storage.commit_step(
            checkpoint=reasoning_checkpoint,
            events=(reasoning_event,),
        )
        return reasoning_checkpoint, None

    async def _execute_tool(self, tool_call: ToolCallRecord) -> ToolResultRecord:
        tool = self._tool_registry.get(tool_call.name)
        if (
            tool is None
            and self._builtin_read_artifact is not None
            and tool_call.name == READ_ARTIFACT_TOOL_NAME
        ):
            tool = self._builtin_read_artifact
        if tool is None:
            return ToolResultRecord(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output=f"unknown tool: {tool_call.name}",
                is_error=True,
            )

        try:
            validated_args = tool.spec.arguments_type.model_validate(
                tool_call.arguments
            )
        except ValidationError as error:
            details = error.errors(include_url=False, include_input=False)
            return ToolResultRecord(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output=f"invalid arguments for tool '{tool_call.name}': {details}",
                is_error=True,
            )

        try:
            output = await tool.execute(validated_args)
        except ToolExecutionError as error:
            return ToolResultRecord(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output=f"tool '{tool_call.name}' failed: {error}",
                is_error=True,
            )

        return ToolResultRecord(
            call_id=tool_call.call_id,
            name=tool_call.name,
            output=output,
            is_error=False,
        )
