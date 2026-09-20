import pytest
from pydantic import ValidationError

from minicode.core.checkpoints import InMemoryCheckpointStore, RunCheckpoint
from minicode.core.context_retrieval import (
    DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
    RunToolResultSource,
)
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.base import ToolExecutionError
from minicode.tools.read_tool_result import (
    ReadToolResultArguments,
    ReadToolResultTool,
)
from minicode.tools.schema import ToolArguments


@pytest.mark.asyncio
async def test_read_tool_result_returns_exact_historical_output() -> None:
    tool = _tool_with_result(
        ToolResult(
            call_id="call_read_before_edit",
            output="timeout = 3\n说明：修改前的值",
        )
    )
    arguments = ReadToolResultArguments.model_validate(
        {"call_id": "call_read_before_edit"}
    )

    output = await tool.execute(arguments)

    assert output == "timeout = 3\n说明：修改前的值"


@pytest.mark.asyncio
async def test_read_tool_result_enforces_utf8_byte_limit() -> None:
    tool = _tool_with_result(
        ToolResult(
            call_id="call_001",
            output="你",
        ),
        max_bytes=2,
    )
    arguments = ReadToolResultArguments.model_validate({"call_id": "call_001"})

    with pytest.raises(
        ToolExecutionError,
        match="historical tool result exceeds 2-byte read limit: call_001",
    ):
        await tool.execute(arguments)


@pytest.mark.asyncio
async def test_read_tool_result_accepts_output_at_default_limit() -> None:
    expected = "x" * DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES
    tool = _tool_with_result(
        ToolResult(
            call_id="call_boundary",
            output=expected,
        )
    )
    arguments = ReadToolResultArguments.model_validate({"call_id": "call_boundary"})

    output = await tool.execute(arguments)

    assert output == expected


@pytest.mark.asyncio
async def test_read_tool_result_converts_lookup_failure_to_tool_error() -> None:
    source = RunToolResultSource(
        InMemoryCheckpointStore(),
        run_id="run_missing",
    )
    tool = ReadToolResultTool(source)
    arguments = ReadToolResultArguments.model_validate({"call_id": "call_001"})

    with pytest.raises(
        ToolExecutionError,
        match="no checkpoint found for run: run_missing",
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(exc_info.value.__cause__, LookupError)


@pytest.mark.parametrize("call_id", ("", " ", "\t"))
def test_read_tool_result_arguments_reject_blank_call_id(call_id: str) -> None:
    with pytest.raises(
        ValidationError,
        match="call_id must not be blank",
    ):
        ReadToolResultArguments.model_validate({"call_id": call_id})


def test_read_tool_result_exposes_model_facing_spec() -> None:
    tool = ReadToolResultTool(
        RunToolResultSource(
            InMemoryCheckpointStore(),
            run_id="run_001",
        )
    )

    spec = tool.spec
    parameters_schema = spec.arguments_type.model_json_schema()

    assert spec.name == "read_tool_result"
    assert spec.description == (
        "Read the exact original output of an earlier tool call in the current "
        "run. This does not execute the earlier tool again."
    )
    assert spec.arguments_type is ReadToolResultArguments
    assert parameters_schema["required"] == ["call_id"]
    assert parameters_schema["additionalProperties"] is False
    assert tool.max_bytes == DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES


@pytest.mark.parametrize(
    ("max_bytes", "error_type", "message"),
    (
        (True, TypeError, "max_bytes must be an integer"),
        (0, ValueError, "max_bytes must be greater than zero"),
    ),
)
def test_read_tool_result_validates_max_bytes(
    max_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    source = RunToolResultSource(
        InMemoryCheckpointStore(),
        run_id="run_001",
    )

    with pytest.raises(error_type, match=message):
        ReadToolResultTool(
            source,
            max_bytes=max_bytes,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_read_tool_result_rejects_wrong_argument_type() -> None:
    tool = ReadToolResultTool(
        RunToolResultSource(
            InMemoryCheckpointStore(),
            run_id="run_001",
        )
    )

    with pytest.raises(
        TypeError,
        match="arguments must be ReadToolResultArguments",
    ):
        await tool.execute(ToolArguments())


def _tool_with_result(
    result: ToolResult,
    *,
    max_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
) -> ReadToolResultTool:
    store = InMemoryCheckpointStore()
    store.save(
        RunCheckpoint(
            run_id="run_001",
            message_history=(
                ToolCall(
                    call_id=result.call_id,
                    name="read_file",
                    arguments={"path": "config.py"},
                ),
                result,
            ),
            turns_used=1,
            tool_calls_used=1,
        )
    )
    return ReadToolResultTool(
        RunToolResultSource(
            store,
            run_id="run_001",
        ),
        max_bytes=max_bytes,
    )
