from unittest.mock import patch

import pytest

from minicode.models.dashscope import (
    DashScopeConfig,
    build_dashscope_client,
    build_dashscope_model,
)


def test_dashscope_config_loads_api_key_and_defaults() -> None:
    environment = {
        "DASHSCOPE_API_KEY": "test-api-key",
    }

    config = DashScopeConfig.from_environment(environment)

    assert config.api_key == "test-api-key"
    assert config.base_url == ("https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert config.model == ("qwen3.7-flash-2026-07-15")


def test_dashscope_config_requires_api_key() -> None:
    environment: dict[str, str] = {}

    with pytest.raises(
        ValueError,
        match="DASHSCOPE_API_KEY is required",
    ):
        DashScopeConfig.from_environment(environment)


@pytest.mark.parametrize(
    "api_key",
    [
        "",
        " ",
        "\t",
    ],
)
def test_dashscope_config_rejects_blank_api_key(
    api_key: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="api_key must not be blank",
    ):
        DashScopeConfig(
            api_key=api_key,
        )


def test_dashscope_config_loads_environment_overrides() -> None:
    environment = {
        "DASHSCOPE_API_KEY": "test-api-key",
        "DASHSCOPE_BASE_URL": (
            "https://llm-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
        "DASHSCOPE_MODEL": "qwen3.7-plus",
    }

    config = DashScopeConfig.from_environment(environment)

    assert config.api_key == "test-api-key"
    assert config.base_url == (
        "https://llm-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert config.model == "qwen3.7-plus"


def test_build_dashscope_client_uses_config() -> None:
    config = DashScopeConfig(
        api_key="test-api-key",
        base_url="https://example.com/compatible-mode/v1",
        model="test-model",
    )

    with patch("minicode.models.dashscope.AsyncOpenAI") as async_openai_type:
        client = build_dashscope_client(config)

    async_openai_type.assert_called_once_with(
        api_key="test-api-key",
        base_url="https://example.com/compatible-mode/v1",
        max_retries=2,
        timeout=60.0,
    )
    assert client is async_openai_type.return_value


def test_build_dashscope_model_wires_client_to_adapter() -> None:
    config = DashScopeConfig(
        api_key="test-api-key",
        base_url="https://example.com/compatible-mode/v1",
        model="test-model",
    )

    with (
        patch("minicode.models.dashscope.build_dashscope_client") as client_builder,
        patch("minicode.models.dashscope.OpenAICompatibleModel") as model_type,
    ):
        model = build_dashscope_model(config)

    client_builder.assert_called_once_with(config)
    model_type.assert_called_once_with(
        client=client_builder.return_value,
        model="test-model",
        extra_body={
            "enable_thinking": False,
        },
    )
    assert model is model_type.return_value


def test_build_dashscope_model_accepts_existing_client() -> None:
    config = DashScopeConfig(
        api_key="test-api-key",
        model="test-model",
    )

    with (
        patch("minicode.models.dashscope.build_dashscope_client") as client_builder,
        patch("minicode.models.dashscope.OpenAICompatibleModel") as model_type,
    ):
        model = build_dashscope_model(
            config,
            client=client_builder.return_value,
        )

    client_builder.assert_not_called()
    model_type.assert_called_once_with(
        client=client_builder.return_value,
        model="test-model",
        extra_body={
            "enable_thinking": False,
        },
    )
    assert model is model_type.return_value
