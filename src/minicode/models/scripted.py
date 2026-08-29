"""Deterministic model implementation for tests and evaluations."""

from collections import deque
from collections.abc import Sequence

from minicode.core.conversation import ConversationItem
from minicode.core.model import ModelRequest, ModelResponse


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
        self._requests: list[ModelRequest] = []

    @property
    def calls(self) -> tuple[tuple[ConversationItem, ...], ...]:
        """Return conversation histories from recorded model requests."""
        return tuple(tuple(request.conversation) for request in self._requests)

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        """Return the complete requests received by this model."""
        return tuple(self._requests)

    async def complete(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """Record the request and return the next prepared response."""
        self._requests.append(request)

        if not self._responses:
            raise RuntimeError("scripted model has no responses remaining")

        return self._responses.popleft()
