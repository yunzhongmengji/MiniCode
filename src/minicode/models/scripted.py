"""Deterministic model implementation for tests and evaluations."""

from collections import deque
from collections.abc import Sequence

from minicode.core.messages import Message
from minicode.core.model import ModelResponse


class ScriptedModel:
    """Return prepared model responses without calling an external provider."""

    def __init__(
        self,
        responses: Sequence[ModelResponse],
    ) -> None:
        if not isinstance(responses, Sequence) or isinstance(
            responses,
            (str, bytes),
        ):
            raise TypeError("responses must be a sequence")

        for response in responses:
            if not isinstance(response, ModelResponse):
                raise TypeError("responses must contain only ModelResponse instances")

        self._responses: deque[ModelResponse] = deque(responses)
        self._calls: list[tuple[Message, ...]] = []

    @property
    def calls(self) -> tuple[tuple[Message, ...], ...]:
        """Return immutable snapshots of received message histories."""
        return tuple(self._calls)

    async def complete(
        self,
        messages: Sequence[Message],
    ) -> ModelResponse:
        """Record the messages and return the next prepared response."""
        self._calls.append(tuple(messages))

        if not self._responses:
            raise RuntimeError("scripted model has no responses remaining")

        return self._responses.popleft()
