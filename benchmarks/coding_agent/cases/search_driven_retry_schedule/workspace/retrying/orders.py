"""Order retry scheduling."""

from retrying.backoff import exponential_delays


def order_retry_delays(
    retry_count: int,
) -> tuple[int, ...]:
    """Return delays used before retrying an order request."""
    return exponential_delays(retry_count)
