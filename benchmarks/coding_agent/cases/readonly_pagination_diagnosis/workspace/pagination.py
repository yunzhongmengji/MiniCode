"""Pagination helpers."""


def page_count(
    total_items: int,
    page_size: int,
) -> int:
    """Return the number of pages needed for total_items."""
    if total_items < 0:
        raise ValueError("total_items must not be negative")

    if page_size <= 0:
        raise ValueError("page_size must be greater than zero")

    return total_items // page_size + 1
