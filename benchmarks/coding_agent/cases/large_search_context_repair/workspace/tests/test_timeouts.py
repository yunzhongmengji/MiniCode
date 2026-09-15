from service_config.client_registry import CLIENT_REQUEST_TIMEOUTS
from service_config.timeouts import DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_all_clients_use_the_thirty_second_shared_default() -> None:
    assert DEFAULT_REQUEST_TIMEOUT_SECONDS == 30
    assert len(CLIENT_REQUEST_TIMEOUTS) == 25
    assert set(CLIENT_REQUEST_TIMEOUTS.values()) == {30}
