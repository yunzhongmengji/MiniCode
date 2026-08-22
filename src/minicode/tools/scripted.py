"""Deterministic tool runtime for tests and evaluations."""

from collections import deque
from collections.abc import Sequence

from minicode.core.tool_calls import ToolCall, ToolResult


class ScriptedToolRuntime:
    """Return prepared tool results without real side effects."""

    def __init__(
        self,
        results: Sequence[ToolResult],
    ) -> None:
        if not isinstance(results, Sequence) or isinstance(
            results,
            (str, bytes),
        ):
            raise TypeError("results must be a sequence")

        for result in results:
            if not isinstance(result, ToolResult):
                raise TypeError("results must contain only ToolResult instances")

        self._results: deque[ToolResult] = deque(results)
        self._calls: list[ToolCall] = []

    @property
    def calls(self) -> tuple[ToolCall, ...]:
        """Return an immutable snapshot of received tool calls."""
        return tuple(self._calls)

    async def execute(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:
        """Record a tool call and return its correlated prepared result."""
        self._calls.append(tool_call)

        if not self._results:
            raise RuntimeError("scripted tool runtime has no results remaining")

        tool_result = self._results[0]

        if tool_result.call_id != tool_call.call_id:
            raise ValueError("tool result call_id must match tool call call_id")

        return self._results.popleft()
