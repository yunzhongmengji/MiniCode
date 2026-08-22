"""Static protocol compatibility checks for model implementations."""

from collections.abc import Sequence

from minicode.core.conversation import ConversationItem
from minicode.core.model import Model, ModelResponse
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
    """Require Model to accept structured conversation history."""
    return await model.complete(history)
