"""Discount calculation helpers."""

from __future__ import annotations


def apply_discount(subtotal: float, discount_rate: float) -> float:
    """Apply a percentage discount once and round to cents."""
    if not 0.0 <= discount_rate <= 1.0:
        raise ValueError("discount_rate must be between 0.0 and 1.0")
    return round(subtotal * (1.0 - discount_rate), 2)
