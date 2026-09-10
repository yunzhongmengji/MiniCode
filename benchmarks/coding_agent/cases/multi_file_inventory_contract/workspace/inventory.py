"""Create records returned by the inventory boundary."""


def inventory_record(
    name: str,
    stock: int,
) -> dict[str, str | int]:
    """Return the public representation of one inventory item."""
    return {
        "name": name,
        "quantity": stock,
    }
