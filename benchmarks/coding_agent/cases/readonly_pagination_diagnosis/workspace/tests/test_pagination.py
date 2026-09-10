from pagination import page_count


def test_exact_multiple_does_not_add_an_extra_page() -> None:
    assert (
        page_count(
            total_items=20,
            page_size=10,
        )
        == 2
    )


def test_empty_collection_needs_no_pages() -> None:
    assert (
        page_count(
            total_items=0,
            page_size=10,
        )
        == 0
    )
