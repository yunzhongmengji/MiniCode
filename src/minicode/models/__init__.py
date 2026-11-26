"""LLM provider adapters and provider-neutral model contracts."""

from minicode.models.base import (
    Model,
    ModelAccessDeniedError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelError,
    ModelProtocolError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelServiceError,
)
from minicode.models.dashscope import (
    DashScopeConfig,
    build_dashscope_client,
    build_dashscope_model,
)
from minicode.models.openai_compatible import OpenAICompatibleModel
from minicode.models.scripted import ScriptedModel

__all__ = [
    "DashScopeConfig",
    "Model",
    "ModelAccessDeniedError",
    "ModelAuthenticationError",
    "ModelConnectionError",
    "ModelError",
    "ModelProtocolError",
    "ModelRateLimitError",
    "ModelRequest",
    "ModelResponse",
    "ModelServiceError",
    "OpenAICompatibleModel",
    "ScriptedModel",
    "build_dashscope_client",
    "build_dashscope_model",
]
