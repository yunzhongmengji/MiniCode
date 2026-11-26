"""Pagination utility."""

from __future__ import annotations


def paginate_items[T](items: list[T], page: int, page_size: int) -> list[T]:
    """Return the 1-indexed page slice of items."""
    # BUG: missing validation for page <= 0 / page_size <= 0 and off-by-one start index.
    start = page * page_size
    return items[start : start + page_size]
