"""Concurrent worker runner."""

from __future__ import annotations

import asyncio

from worker.counter import SharedCounter


async def run_batch(concurrency: int) -> int:
    """Run `concurrency` parallel increments and return the final total."""
    counter = SharedCounter()
    await asyncio.gather(*(counter.increment() for _ in range(concurrency)))
    return counter.value
