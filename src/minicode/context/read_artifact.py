"""Built-in read_artifact tool for retrieving compressed tool outputs from the Ledger."""

from __future__ import annotations

from contextvars import ContextVar

from pydantic import Field

from minicode.schemas.events import EventType
from minicode.storage.event_ledger import EventLedger
from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec

READ_ARTIFACT_TOOL_NAME = "read_artifact"

active_session_id_var: ContextVar[str | None] = ContextVar(
    "minicode_active_session_id",
    default=None,
)


class ReadArtifactArguments(ToolArguments):
    """Input schema for retrieving one compressed tool output by event_id."""

    event_id: int = Field(ge=1)
    offset_chars: int = Field(default=0, ge=0)
    max_chars: int | None = Field(default=None, ge=1)


class ReadArtifactTool:
    """Retrieve original tool output from the SQLite Event Ledger by event_id."""

    def __init__(
        self,
        *,
        event_ledger: EventLedger,
        session_id: str | None = None,
    ) -> None:
        self._event_ledger = event_ledger
        self._fixed_session_id = session_id
        self._spec = ToolSpec(
            name=READ_ARTIFACT_TOOL_NAME,
            description=(
                "Read the original uncompressed output of a previously compressed "
                "tool result from the Event Ledger using its event_id."
            ),
            arguments_type=ReadArtifactArguments,
        )

    @property
    def spec(self) -> ToolSpec:
        """Return tool metadata for model tool-calling."""
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        """Fetch and return the original tool output for the given event_id."""
        if not isinstance(arguments, ReadArtifactArguments):
            raise TypeError("arguments must be ReadArtifactArguments")

        session_id = (
            self._fixed_session_id
            if self._fixed_session_id is not None
            else active_session_id_var.get()
        )
        if session_id is None:
            raise ToolExecutionError("read_artifact requires an active session context")

        event = self._event_ledger.get_event(
            arguments.event_id,
            session_id=session_id,
        )
        if event is None:
            raise ToolExecutionError(
                f"artifact event_id={arguments.event_id} not found in session '{session_id}'"
            )

        if event.event_type is not EventType.TOOL_EXECUTED:
            raise ToolExecutionError(
                f"event_id={arguments.event_id} is not a tool_executed event "
                f"(found '{event.event_type.value}')"
            )

        output = event.payload.get("output")
        if not isinstance(output, str):
            raise ToolExecutionError(
                f"event_id={arguments.event_id} does not contain text output"
            )

        start = arguments.offset_chars
        if arguments.max_chars is None:
            return output[start:]
        return output[start : start + arguments.max_chars]
