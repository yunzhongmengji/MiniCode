"""Deterministic model implementation for tests and offline evaluations."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from minicode.models.base import ModelRequest, ModelResponse
from minicode.schemas.messages import HistoryEntry


class ScriptedModel:
    """Return prepared ModelResponse items without calling an external provider."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses: deque[ModelResponse] = deque(responses)
        self._requests: list[ModelRequest] = []

    @property
    def calls(self) -> tuple[tuple[HistoryEntry, ...], ...]:
        """Return conversation histories from recorded model requests."""
        return tuple(request.conversation for request in self._requests)

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        """Return the complete requests received by this model."""
        return tuple(self._requests)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Record the request and return the next prepared response."""
        self._requests.append(request)
        if not self._responses:
            raise RuntimeError("scripted model has no responses remaining")
        return self._responses.popleft()
