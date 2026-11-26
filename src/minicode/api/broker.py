"""In-memory pub/sub broker bridging committed LedgerEvents to SSE queues."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from minicode.schemas.events import LedgerEvent


class TaskEventBroker:
    """Publish committed events to active SSE subscribers per session_id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[LedgerEvent]]] = defaultdict(set)

    def publish(self, events: tuple[LedgerEvent, ...]) -> None:
        """Fan out committed events to all active SSE subscribers for their session."""
        for event in events:
            queues = self._subscribers.get(event.session_id)
            if not queues:
                continue
            for queue in tuple(queues):
                queue.put_nowait(event)

    def subscribe(self, session_id: str) -> asyncio.Queue[LedgerEvent]:
        """Register a new subscriber queue for one session."""
        queue: asyncio.Queue[LedgerEvent] = asyncio.Queue()
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[LedgerEvent]) -> None:
        """Remove a subscriber queue when an SSE client disconnects."""
        queues = self._subscribers.get(session_id)
        if queues is not None:
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(session_id, None)
