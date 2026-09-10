"""Shared retry backoff calculation."""


def exponential_delays(
    attempts: int,
    *,
    base_seconds: int = 1,
) -> tuple[int, ...]:
    """Return one exponential delay for each retry attempt."""
    if attempts < 0:
        raise ValueError("attempts must not be negative")

    if base_seconds <= 0:
        raise ValueError("base_seconds must be greater than zero")

    return tuple(
        base_seconds * 2**attempt
        for attempt in range(
            1,
            attempts + 1,
        )
    )
