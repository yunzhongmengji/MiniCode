import pytest

from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.scripted import ScriptedToolRuntime


@pytest.mark.asyncio
async def test_scripted_tool_runtime_returns_result_and_records_call() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )
    runtime = ScriptedToolRuntime(
        results=[tool_result],
    )

    result = await runtime.execute(tool_call)

    assert result == tool_result
    assert runtime.calls == (tool_call,)


@pytest.mark.asyncio
async def test_scripted_tool_runtime_rejects_mismatched_call_id() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    mismatched_result = ToolResult(
        call_id="call_002",
        output="Wrong result.",
    )
    runtime = ScriptedToolRuntime(
        results=[mismatched_result],
    )

    with pytest.raises(
        ValueError,
        match="tool result call_id must match tool call call_id",
    ):
        await runtime.execute(tool_call)

    assert runtime.calls == (tool_call,)


@pytest.mark.asyncio
async def test_scripted_tool_runtime_reports_exhausted_results() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    runtime = ScriptedToolRuntime(
        results=[],
    )

    with pytest.raises(
        RuntimeError,
        match="scripted tool runtime has no results remaining",
    ):
        await runtime.execute(tool_call)

    assert runtime.calls == (tool_call,)


def test_scripted_tool_runtime_rejects_non_tool_result() -> None:
    with pytest.raises(
        TypeError,
        match="results must contain only ToolResult instances",
    ):
        ScriptedToolRuntime(
            results=["not a tool result"],
        )


@pytest.mark.parametrize(
    "results",
    [
        {},
        "",
        b"",
    ],
)
def test_scripted_tool_runtime_rejects_invalid_result_container(
    results: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="results must be a sequence",
    ):
        ScriptedToolRuntime(
            results=results,
        )
