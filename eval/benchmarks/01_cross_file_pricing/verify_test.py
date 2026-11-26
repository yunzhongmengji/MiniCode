"""Independent pytest verifier for 01_cross_file_pricing."""

from __future__ import annotations

from pricing.checkout import calculate_total


def test_regular_order_no_discount() -> None:
    assert calculate_total([50.0, 50.0], 0.0) == 100.0


def test_vip_order_single_discount() -> None:
    assert calculate_total([100.0, 100.0], 0.2) == 160.0


def test_full_discount_zero_total() -> None:
    assert calculate_total([42.5], 1.0) == 0.0
