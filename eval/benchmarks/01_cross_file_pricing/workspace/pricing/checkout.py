"""Checkout total computation."""

from __future__ import annotations

from pricing.discounts import apply_discount


def calculate_total(items: list[float], discount_rate: float = 0.0) -> float:
    """Compute final checkout total from item prices and discount rate."""
    subtotal = sum(items)
    discounted = apply_discount(subtotal, discount_rate)
    # BUG: applies discount_rate a second time after apply_discount already applied it.
    return round(discounted * (1.0 - discount_rate), 2)
