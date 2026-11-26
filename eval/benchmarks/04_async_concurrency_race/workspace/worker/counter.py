"""Shared async counter."""

from __future__ import annotations

import asyncio


class SharedCounter:
    """Async counter incremented by concurrent worker coroutines."""

    def __init__(self) -> None:
        self.value = 0

    async def increment(self) -> int:
        """Increment the counter by 1 safely across concurrent tasks."""
        # BUG: unprotected read-modify-write across an await yield point.
        current = self.value
        await asyncio.sleep(0)
        self.value = current + 1
        return self.value
