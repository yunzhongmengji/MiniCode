from inventory import inventory_record
from report import render_inventory


def test_inventory_record_uses_stock_field() -> None:
    assert inventory_record(
        "keyboard",
        3,
    ) == {
        "name": "keyboard",
        "stock": 3,
    }


def test_report_reads_stock_field() -> None:
    assert (
        render_inventory(
            {
                "name": "keyboard",
                "stock": 3,
            }
        )
        == "keyboard: 3 units in stock"
    )
