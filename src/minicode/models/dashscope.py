"""Alibaba Cloud Model Studio configuration and composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen3.7-flash-2026-07-15"


@dataclass(frozen=True, slots=True)
class DashScopeConfig:
    """Configuration required to call Alibaba Cloud Model Studio."""

    api_key: str = field(repr=False)
    base_url: str = _DEFAULT_BASE_URL
    model: str = _DEFAULT_MODEL

    def __post_init__(self) -> None:
        """Validate the completed DashScope configuration."""
        if not self.api_key.strip():
            raise ValueError("api_key must not be blank")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> DashScopeConfig:
        """Create configuration from environment-style values."""
        api_key = environment.get("DASHSCOPE_API_KEY")

        if api_key is None:
            raise ValueError("DASHSCOPE_API_KEY is required")

        return cls(
            api_key=api_key,
            base_url=environment.get(
                "DASHSCOPE_BASE_URL",
                _DEFAULT_BASE_URL,
            ),
            model=environment.get(
                "DASHSCOPE_MODEL",
                _DEFAULT_MODEL,
            ),
        )


def build_dashscope_client(
    config: DashScopeConfig,
) -> AsyncOpenAI:
    """Create an asynchronous SDK client from DashScope configuration."""
    return AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        max_retries=2,
        timeout=60.0,
    )


def build_dashscope_model(
    config: DashScopeConfig,
) -> OpenAICompatibleModel:
    """Create a MiniCode model adapter for Alibaba Cloud Model Studio."""
    client = build_dashscope_client(config)

    return OpenAICompatibleModel(
        client=client,
        model=config.model,
        extra_body={
            "enable_thinking": False,
        },
    )
