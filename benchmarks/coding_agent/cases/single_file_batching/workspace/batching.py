"""Small batching helper used by the evaluation fixture."""

from collections.abc import Sequence


def batches[Item](
    items: Sequence[Item],
    size: int,
) -> list[list[Item]]:
    """Split items into consecutive lists containing at most size items."""
    if size <= 0:
        raise ValueError("size must be greater than zero")

    return [
        list(items[start : start + size])
        for start in range(
            0,
            len(items),
            size + 1,
        )
    ]
