import asyncio
from hashlib import sha256

import pytest

from minicode.core.artifacts import (
    InMemoryArtifactStore,
)
from minicode.core.events import (
    EventKind,
    InMemoryEventLedger,
    LedgerEvent,
)
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.models.scripted import ScriptedModel
from minicode.tools.base import ToolExecutionError
from minicode.tools.dispatcher import ToolDispatcher
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


def _allow_tools(
    *tool_names: str,
) -> ConfiguredToolPolicy:
    """Build explicit allow rules for dispatcher tests."""
    return ConfiguredToolPolicy(
        decisions={
            tool_name: PolicyDecision(
                outcome=PolicyOutcome.ALLOW,
                reason="allowed by test policy",
            )
            for tool_name in tool_names
        },
    )


class RecordingApprover:
    """Return a scripted answer and record approval requests."""

    def __init__(
        self,
        *,
        approved: bool,
    ) -> None:
        self._approved = approved
        self.requests: list[tuple[ToolCall, str]] = []

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        self.requests.append(
            (
                tool_call,
                reason,
            )
        )
        return self._approved


class InvalidResultApprover:
    """Return an invalid result from the approval boundary."""

    def __init__(
        self,
        result: object,
    ) -> None:
        self._result = result

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        del tool_call, reason

        return self._result  # type: ignore[return-value]


class InvalidResultPolicy:
    """Return an invalid result from the policy boundary."""

    def __init__(
        self,
        result: object,
    ) -> None:
        self._result = result

    def evaluate(
        self,
        tool_call: ToolCall,
    ) -> PolicyDecision:
        del tool_call

        return self._result  # type: ignore[return-value]


class EchoArguments(ToolArguments):
    """Arguments accepted by the test echo tool."""

    text: str


class EchoTool:
    """Record and return validated text during dispatcher tests."""

    def __init__(self) -> None:
        self.received_arguments: list[EchoArguments] = []

    @property
    def spec(self) -> ToolSpec:
        """Return metadata describing the echo tool."""
        return ToolSpec(
            name="echo",
            description="Return the supplied text.",
            arguments_type=EchoArguments,
        )

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Record validated arguments and return their text."""
        if not isinstance(arguments, EchoArguments):
            raise TypeError("arguments must be EchoArguments")

        self.received_arguments.append(arguments)
        return arguments.text


class FailingEchoTool(EchoTool):
    """Echo tool that reports an expected operational failure."""

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Raise a controlled tool execution error."""
        raise ToolExecutionError("echo backend is unavailable")


class CrashingEchoTool(EchoTool):
    """Echo tool that raises an unexpected failure."""

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Raise an unexpected programming failure."""
        del arguments

        raise RuntimeError("unexpected echo crash")


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_unknown_tool() -> None:
    registry = ToolRegistry()
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools(),
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="missing_tool",
        arguments={},
    )

    result = await dispatcher.execute(tool_call)

    assert result.call_id == "call_001"
    assert result.output == "unknown tool: missing_tool"
    assert result.is_error is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "outcome",
        "expected_output",
    ),
    [
        (
            PolicyOutcome.DENY,
            "tool 'echo' denied by policy",
        ),
        (
            PolicyOutcome.ASK,
            "tool 'echo' requires approval",
        ),
    ],
)
async def test_dispatcher_does_not_execute_unapproved_tool(
    outcome: PolicyOutcome,
    expected_output: str,
) -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    policy = ConfiguredToolPolicy(
        decisions={
            "echo": PolicyDecision(
                outcome=outcome,
                reason="test policy rule",
            ),
        },
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "must not execute",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output=expected_output,
        is_error=True,
    )
    assert tool.received_arguments == []


@pytest.mark.asyncio
async def test_dispatcher_records_policy_decision() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    policy = ConfiguredToolPolicy(
        decisions={
            "echo": PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="blocked by test policy",
            ),
        },
    )
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        event_ledger=ledger,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "must not execute",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result.is_error is True
    assert tool.received_arguments == []
    assert ledger.events == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.TOOL_POLICY_DECIDED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "deny",
                "reason": "blocked by test policy",
            },
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "approved",
        "expected_output",
        "expected_error",
        "expected_arguments",
    ),
    [
        (
            True,
            "hello",
            False,
            [
                EchoArguments(
                    text="hello",
                )
            ],
        ),
        (
            False,
            "tool 'echo' approval denied",
            True,
            [],
        ),
    ],
)
async def test_dispatcher_resolves_ask_with_approval(
    approved: bool,
    expected_output: str,
    expected_error: bool,
    expected_arguments: list[EchoArguments],
) -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    reason = "workspace writes require approval"
    policy = ConfiguredToolPolicy(
        decisions={
            "echo": PolicyDecision(
                outcome=PolicyOutcome.ASK,
                reason=reason,
            ),
        },
    )
    approver = RecordingApprover(
        approved=approved,
    )
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        approver=approver,
        event_ledger=ledger,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output=expected_output,
        is_error=expected_error,
    )
    assert approver.requests == [
        (
            tool_call,
            reason,
        )
    ]
    assert tool.received_arguments == (expected_arguments)
    assert ledger.events[:2] == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.TOOL_POLICY_DECIDED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "ask",
                "reason": reason,
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.TOOL_APPROVAL_RESOLVED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "approved": approved,
            },
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "approval_result",
    [
        None,
        1,
        "yes",
    ],
)
async def test_dispatcher_rejects_invalid_approval_result(
    approval_result: object,
) -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    policy = ConfiguredToolPolicy(
        decisions={
            "echo": PolicyDecision(
                outcome=PolicyOutcome.ASK,
                reason="approval is required",
            ),
        },
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        approver=InvalidResultApprover(approval_result),
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "must not execute",
        },
    )

    with pytest.raises(
        TypeError,
        match=("approver must return a boolean"),
    ):
        await dispatcher.execute(tool_call)

    assert tool.received_arguments == []


@pytest.mark.asyncio
async def test_dispatcher_validates_and_executes_registered_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    artifact_store = InMemoryArtifactStore()
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
        event_ledger=ledger,
        artifact_store=artifact_store,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result.call_id == "call_001"
    assert result.output == "hello"
    assert result.is_error is False
    assert tool.received_arguments == [
        EchoArguments(
            text="hello",
        )
    ]
    assert ledger.events == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.TOOL_POLICY_DECIDED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "allow",
                "reason": "allowed by test policy",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.TOOL_EXECUTION_STARTED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.TOOL_EXECUTION_FINISHED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "succeeded",
                "output_artifact": {
                    "artifact_id": (f"sha256:{sha256(b'hello').hexdigest()}"),
                    "media_type": "text/plain",
                    "byte_count": 5,
                },
            },
        ),
    )
    artifact_id = f"sha256:{sha256(b'hello').hexdigest()}"

    assert artifact_store.read_text(artifact_id) == "hello"


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_invalid_arguments() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": 123,
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result.call_id == "call_001"
    assert "invalid arguments for tool 'echo'" in result.output
    assert "text" in result.output
    assert result.is_error is True
    assert tool.received_arguments == []


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_tool_execution_failure() -> None:
    registry = ToolRegistry()
    registry.register(FailingEchoTool())
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    artifact_store = InMemoryArtifactStore()
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
        event_ledger=ledger,
        artifact_store=artifact_store,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )
    expected_output = "tool 'echo' failed: echo backend is unavailable"

    result = await dispatcher.execute(tool_call)

    assert result.call_id == "call_001"
    assert result.output == expected_output
    assert result.is_error is True
    assert ledger.events == (
        LedgerEvent(
            run_id="run_001",
            sequence=1,
            kind=EventKind.TOOL_POLICY_DECIDED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "allow",
                "reason": "allowed by test policy",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.TOOL_EXECUTION_STARTED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.TOOL_EXECUTION_FINISHED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "failed",
                "error_type": "ToolExecutionError",
                "output_artifact": {
                    "artifact_id": (
                        f"sha256:{sha256(expected_output.encode('utf-8')).hexdigest()}"
                    ),
                    "media_type": "text/plain",
                    "byte_count": len(expected_output.encode("utf-8")),
                },
            },
        ),
    )
    artifact_id = f"sha256:{sha256(expected_output.encode('utf-8')).hexdigest()}"

    assert artifact_store.read_text(artifact_id) == expected_output


@pytest.mark.asyncio
async def test_dispatcher_records_and_reraises_unexpected_tool_failure() -> None:
    registry = ToolRegistry()
    registry.register(CrashingEchoTool())
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
        event_ledger=ledger,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )

    with pytest.raises(
        RuntimeError,
        match="unexpected echo crash",
    ):
        await dispatcher.execute(tool_call)

    assert ledger.events[-2:] == (
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.TOOL_EXECUTION_STARTED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.TOOL_EXECUTION_FINISHED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "failed",
                "error_type": "RuntimeError",
            },
        ),
    )


@pytest.mark.asyncio
async def test_dispatcher_records_and_reraises_tool_cancellation() -> None:
    tool_started = asyncio.Event()
    tool_cleaned_up = asyncio.Event()

    class WaitingEchoTool(EchoTool):
        async def execute(
            self,
            arguments: ToolArguments,
        ) -> str:
            del arguments
            tool_started.set()

            try:
                await asyncio.Event().wait()
            finally:
                tool_cleaned_up.set()

            raise AssertionError("unreachable")

    registry = ToolRegistry()
    registry.register(WaitingEchoTool())
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
        event_ledger=ledger,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )

    task = asyncio.create_task(dispatcher.execute(tool_call))

    await tool_started.wait()

    task.cancel()

    with pytest.raises(
        asyncio.CancelledError,
    ):
        await task

    assert tool_cleaned_up.is_set()
    assert ledger.events[-2:] == (
        LedgerEvent(
            run_id="run_001",
            sequence=2,
            kind=EventKind.TOOL_EXECUTION_STARTED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
            },
        ),
        LedgerEvent(
            run_id="run_001",
            sequence=3,
            kind=EventKind.TOOL_EXECUTION_FINISHED,
            payload={
                "call_id": "call_001",
                "tool_name": "echo",
                "outcome": "cancelled",
            },
        ),
    )


@pytest.mark.asyncio
async def test_query_loop_executes_tool_through_dispatcher() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "hello",
        },
    )
    first_response = ModelResponse(
        content="",
        tool_calls=(tool_call,),
    )
    final_response = ModelResponse(
        content="The echo tool returned hello.",
    )
    model = ScriptedModel(
        responses=[
            first_response,
            final_response,
        ]
    )
    ledger = InMemoryEventLedger(
        run_id="run_001",
    )
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=_allow_tools("echo"),
        event_ledger=ledger,
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=dispatcher,
        max_turns=2,
        event_ledger=ledger,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Echo hello.",
        ),
    )

    result = await loop.run(initial_history)

    tool_result = ToolResult(
        call_id="call_001",
        output="hello",
        is_error=False,
    )
    second_history = initial_history + (
        tool_call,
        tool_result,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.response == final_response
    assert result.turns_used == 2
    assert result.message_history == second_history
    assert model.calls == (
        initial_history,
        second_history,
    )
    assert tool.received_arguments == [
        EchoArguments(
            text="hello",
        )
    ]
    assert tuple(event.kind for event in ledger.events) == (
        EventKind.RUN_STARTED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.TOOL_POLICY_DECIDED,
        EventKind.TOOL_EXECUTION_STARTED,
        EventKind.TOOL_EXECUTION_FINISHED,
        EventKind.MODEL_CALL_STARTED,
        EventKind.MODEL_CALL_FINISHED,
        EventKind.RUN_FINISHED,
    )

    assert tuple(event.sequence for event in ledger.events) == tuple(range(1, 10))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy_result",
    [
        None,
        "allow",
        PolicyOutcome.ALLOW,
    ],
)
async def test_dispatcher_rejects_invalid_policy_result(
    policy_result: object,
) -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=InvalidResultPolicy(policy_result),
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "must not execute",
        },
    )

    with pytest.raises(
        TypeError,
        match=("policy must return a PolicyDecision"),
    ):
        await dispatcher.execute(tool_call)

    assert tool.received_arguments == []


@pytest.mark.asyncio
async def test_dispatcher_validates_arguments_before_policy() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    approver = RecordingApprover(
        approved=True,
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=InvalidResultPolicy(None),
        approver=approver,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": 123,
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result.call_id == "call_001"
    assert "invalid arguments for tool 'echo'" in (result.output)
    assert result.is_error is True
    assert approver.requests == []
    assert tool.received_arguments == []


@pytest.mark.asyncio
async def test_dispatcher_does_not_ask_approval_for_denied_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    policy = ConfiguredToolPolicy(
        decisions={
            "echo": PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="tool is forbidden",
            ),
        },
    )
    approver = RecordingApprover(
        approved=True,
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        approver=approver,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="echo",
        arguments={
            "text": "must not execute",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output="tool 'echo' denied by policy",
        is_error=True,
    )
    assert approver.requests == []
    assert tool.received_arguments == []
