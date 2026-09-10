"""Notification retry scheduling."""

from retrying.backoff import exponential_delays


def notification_retry_delays(
    retry_count: int,
) -> tuple[int, ...]:
    """Return delays used before retrying a notification."""
    return exponential_delays(retry_count)
