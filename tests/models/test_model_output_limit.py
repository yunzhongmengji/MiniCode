"""Check the SDK keyword actually sent, without network calls."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest
from minicode.models.openai_compatible import OpenAICompatibleModel


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 1024])
async def test_sdk_completion_output_limit_is_optional(limit) -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "limit-test",
            "created": 0,
            "model": "fixed-model",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Done"},
                }
            ],
        }
    )
    client = MagicMock(spec=AsyncOpenAI)
    client.chat.completions.create = AsyncMock(return_value=completion)
    model = OpenAICompatibleModel(
        client=client, model="fixed-model", max_output_tokens=limit
    )
    await model.complete(
        ModelRequest(conversation=(Message(role=MessageRole.USER, content="task"),))
    )
    kwargs = client.chat.completions.create.call_args.kwargs
    if limit is None:
        assert "max_completion_tokens" not in kwargs
    else:
        assert kwargs["max_completion_tokens"] == 1024


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_sdk_output_limit_validation(limit) -> None:
    with pytest.raises((TypeError, ValueError)):
        OpenAICompatibleModel(
            client=MagicMock(spec=AsyncOpenAI),
            model="fixed-model",
            max_output_tokens=limit,
        )


@pytest.mark.asyncio
async def test_stream_sends_the_same_output_limit() -> None:
    async def chunks():
        yield ChatCompletionChunk.model_validate(
            {
                "id": "limit-stream",
                "created": 0,
                "model": "fixed-model",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "delta": {"content": "Done"}}
                ],
            }
        )

    client = MagicMock(spec=AsyncOpenAI)
    client.chat.completions.create = AsyncMock(return_value=chunks())
    model = OpenAICompatibleModel(
        client=client, model="fixed-model", max_output_tokens=1024
    )
    request = ModelRequest(
        conversation=(Message(role=MessageRole.USER, content="task"),)
    )
    events = [event async for event in model.stream(request)]
    assert events
    assert (
        client.chat.completions.create.call_args.kwargs["max_completion_tokens"] == 1024
    )
