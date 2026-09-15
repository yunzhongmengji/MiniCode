"""Tool for reading one historical result from the current run."""

import asyncio

from pydantic import Field, field_validator

from minicode.core.context_retrieval import (
    RunToolResultSource,
    ToolResultLookupError,
)
from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec

_DEFAULT_MAX_BYTES = 50_000


class ReadToolResultArguments(ToolArguments):
    """Validated arguments accepted by historical-result retrieval."""

    call_id: str = Field(
        description=("Call ID of an earlier tool result in the current run's history."),
    )

    @field_validator("call_id")
    @classmethod
    def validate_call_id_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject call IDs containing only whitespace."""
        if not value.strip():
            raise ValueError("call_id must not be blank")

        return value


_READ_TOOL_RESULT_SPEC = ToolSpec(
    name="read_tool_result",
    description=(
        "Read the exact original output of an earlier tool call in the current "
        "run. This does not execute the earlier tool again."
    ),
    arguments_type=ReadToolResultArguments,
)


class ReadToolResultTool:
    """Expose bounded historical-result retrieval as a read-only tool."""

    def __init__(
        self,
        source: RunToolResultSource,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        self._source = source
        self._max_bytes = max_bytes

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _READ_TOOL_RESULT_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Return one bounded historical tool output without re-execution."""
        if not isinstance(arguments, ReadToolResultArguments):
            raise TypeError("arguments must be ReadToolResultArguments")

        try:
            result = await asyncio.to_thread(
                self._source.get,
                arguments.call_id,
            )
        except ToolResultLookupError as error:
            raise ToolExecutionError(str(error)) from error

        output_bytes = len(result.output.encode("utf-8"))

        if output_bytes > self._max_bytes:
            raise ToolExecutionError(
                "historical tool result exceeds "
                f"{self._max_bytes}-byte read limit: {arguments.call_id}"
            )

        return result.output
