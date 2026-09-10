"""Render public inventory records for terminal output."""

from collections.abc import Mapping


def render_inventory(
    record: Mapping[str, str | int],
) -> str:
    """Render one inventory record."""
    return f"{record['name']}: {record['quantity']} units in stock"
