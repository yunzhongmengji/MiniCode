import pytest
from batching import batches


def test_batches_preserve_every_item_in_order() -> None:
    assert batches(
        [1, 2, 3, 4, 5],
        2,
    ) == [
        [1, 2],
        [3, 4],
        [5],
    ]


def test_batches_reject_non_positive_size() -> None:
    with pytest.raises(
        ValueError,
        match="size must be greater than zero",
    ):
        batches(
            [1, 2],
            0,
        )
