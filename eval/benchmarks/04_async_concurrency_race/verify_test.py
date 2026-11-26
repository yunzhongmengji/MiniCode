"""Independent pytest verifier for 04_async_concurrency_race."""

from __future__ import annotations

import asyncio

from worker.runner import run_batch


def test_concurrent_increments_do_not_lose_updates() -> None:
    total = asyncio.run(run_batch(50))
    assert total == 50
