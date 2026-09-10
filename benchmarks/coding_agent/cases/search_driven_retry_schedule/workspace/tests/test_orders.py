from retrying.orders import order_retry_delays


def test_order_retries_start_at_base_delay() -> None:
    assert order_retry_delays(3) == (
        1,
        2,
        4,
    )
