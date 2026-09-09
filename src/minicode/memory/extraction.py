"""Memory extraction contracts and test implementations."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from minicode.core.conversation import (
    ConversationItem,
)
from minicode.core.messages import Message
from minicode.core.model import (
    ModelResponse,
)
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.memory.records import (
    MemoryProposal,
    MemoryScope,
)


@dataclass(frozen=True, slots=True)
class MemoryExtractionRequest:
    """Information available after one completed run."""

    run_id: str
    scope: MemoryScope
    message_history: Sequence[ConversationItem]
    response: ModelResponse

    def __post_init__(self) -> None:
        """Validate and snapshot extraction input."""
        if not isinstance(
            self.run_id,
            str,
        ):
            raise TypeError("run_id must be a string")

        if not self.run_id.strip():
            raise ValueError("run_id must not be blank")

        if not isinstance(
            self.scope,
            MemoryScope,
        ):
            raise TypeError("scope must be a MemoryScope")

        if not isinstance(
            self.message_history,
            Sequence,
        ) or isinstance(
            self.message_history,
            (str, bytes),
        ):
            raise TypeError("message_history must be a sequence")

        history = tuple(self.message_history)

        for item in history:
            if not isinstance(
                item,
                (
                    Message,
                    ToolCall,
                    ToolResult,
                ),
            ):
                raise TypeError(
                    "message_history must contain only ConversationItem instances"
                )

        if not isinstance(
            self.response,
            ModelResponse,
        ):
            raise TypeError("response must be a ModelResponse")

        object.__setattr__(
            self,
            "message_history",
            history,
        )


class MemoryExtractor(Protocol):
    """Propose memories from one completed run."""

    async def extract(
        self,
        request: MemoryExtractionRequest,
    ) -> tuple[MemoryProposal, ...]:
        """Return proposed memories without saving them."""
        ...


class ScriptedMemoryExtractor:
    """Return prepared candidates for deterministic tests."""

    def __init__(
        self,
        candidates: Sequence[MemoryProposal],
    ) -> None:
        self._candidates = tuple(candidates)
        self._requests: list[MemoryExtractionRequest] = []

    @property
    def requests(
        self,
    ) -> tuple[
        MemoryExtractionRequest,
        ...,
    ]:
        """Return recorded extraction requests."""
        return tuple(self._requests)

    async def extract(
        self,
        request: MemoryExtractionRequest,
    ) -> tuple[MemoryProposal, ...]:
        """Record the request and return prepared candidates."""
        self._requests.append(request)

        return self._candidates
