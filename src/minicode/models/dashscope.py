"""Alibaba Cloud Model Studio configuration and composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen3.7-flash"


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
    *,
    max_retries: int = 2,
) -> AsyncOpenAI:
    """Create an asynchronous SDK client from DashScope configuration."""
    return AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        max_retries=max_retries,
        timeout=60.0,
    )


def build_dashscope_model(
    config: DashScopeConfig,
    *,
    client: AsyncOpenAI | None = None,
    max_output_tokens: int | None = None,
) -> OpenAICompatibleModel:
    """Create a MiniCode model adapter for Alibaba Cloud Model Studio."""
    resolved_client = build_dashscope_client(config) if client is None else client

    if max_output_tokens is not None:
        return OpenAICompatibleModel(
            client=resolved_client,
            model=config.model,
            extra_body={"enable_thinking": False, "temperature": 0.0},
            max_output_tokens=max_output_tokens,
        )

    return OpenAICompatibleModel(
        client=resolved_client,
        model=config.model,
        extra_body={
            "enable_thinking": False,
        },
    )
