import pytest

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelResponse
from minicode.core.query_loop import QueryLoop, StopReason
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.base import ToolExecutionError
from minicode.tools.dispatcher import ToolDispatcher
from minicode.tools.registry import ToolRegistry
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


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


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_unknown_tool() -> None:
    registry = ToolRegistry()
    dispatcher = ToolDispatcher(
        registry=registry,
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
async def test_dispatcher_validates_and_executes_registered_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
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


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_invalid_arguments() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
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
    dispatcher = ToolDispatcher(
        registry=registry,
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
    assert result.output == ("tool 'echo' failed: echo backend is unavailable")
    assert result.is_error is True


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

    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    dispatcher = ToolDispatcher(
        registry=registry,
    )
    loop = QueryLoop(
        model=model,
        tool_runtime=dispatcher,
        max_turns=2,
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
