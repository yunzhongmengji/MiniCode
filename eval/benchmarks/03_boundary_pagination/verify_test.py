"""Independent pytest verifier for 03_boundary_pagination."""

from __future__ import annotations

import pytest
from service.catalog import list_catalog_page
from service.pagination import paginate_items


def test_first_and_last_pages() -> None:
    products = ["a", "b", "c", "d", "e"]
    assert list_catalog_page(products, page=1, page_size=2)["items"] == ["a", "b"]
    assert list_catalog_page(products, page=3, page_size=2)["items"] == ["e"]
    assert list_catalog_page(products, page=4, page_size=2)["items"] == []


def test_empty_and_invalid_bounds() -> None:
    assert paginate_items([], page=1, page_size=5) == []
    with pytest.raises(ValueError):
        paginate_items(["a"], page=0, page_size=2)
    with pytest.raises(ValueError):
        paginate_items(["a"], page=1, page_size=0)
