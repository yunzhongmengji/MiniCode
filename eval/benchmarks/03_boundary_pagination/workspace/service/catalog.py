"""Catalog listing backed by pagination."""

from __future__ import annotations

from service.pagination import paginate_items


def list_catalog_page(
    products: list[str],
    *,
    page: int = 1,
    page_size: int = 2,
) -> dict[str, object]:
    """Return paginated catalog entries and total count."""
    return {
        "page": page,
        "total": len(products),
        "items": paginate_items(products, page, page_size),
    }
