"""Static protocol checks for streaming model implementations."""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from minicode.core.model import (
    ModelRequest,
    ModelResponse,
    ModelResponseDone,
    ModelStreamEvent,
    ModelTextDelta,
    StreamingModel,
)
from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
)


class ExampleStreamingModel:
    """Minimal structurally compatible streaming model."""

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        del request

        yield ModelTextDelta(
            text="MINICODE",
        )
        yield ModelResponseDone(
            response=ModelResponse(
                content="MINICODE",
            ),
        )


def build_streaming_model() -> StreamingModel:
    """Require the example to satisfy StreamingModel."""
    return ExampleStreamingModel()


def build_openai_compatible_streaming_model(
    client: AsyncOpenAI,
) -> StreamingModel:
    """Require OpenAICompatibleModel to satisfy StreamingModel."""
    return OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
