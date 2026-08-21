"""Static protocol compatibility checks for model implementations."""

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
