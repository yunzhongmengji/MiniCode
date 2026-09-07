"""Static protocol compatibility checks for model implementations."""

from collections.abc import Sequence

from openai import AsyncOpenAI

from minicode.core.conversation import ConversationItem
from minicode.core.model import Model, ModelRequest, ModelResponse
from minicode.core.model_metrics import RecordingModel
from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
)
from minicode.models.scripted import ScriptedModel


def build_scripted_model_as_protocol() -> Model:
    """Require ScriptedModel to satisfy the Model protocol."""
    return ScriptedModel(
        responses=[
            ModelResponse(
                content="Ready.",
            ),
        ]
    )


async def complete_structured_history(
    model: Model,
    history: Sequence[ConversationItem],
) -> ModelResponse:
    """Require Model to accept a request containing structured history."""
    request = ModelRequest(
        conversation=history,
    )
    return await model.complete(request)


def build_openai_compatible_model_as_protocol(
    client: AsyncOpenAI,
) -> Model:
    """Require OpenAICompatibleModel to satisfy the Model protocol."""
    return OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )


def build_recording_model_as_protocol(
    model: Model,
) -> Model:
    """Require RecordingModel to satisfy the Model protocol."""
    return RecordingModel(
        model=model,
    )
