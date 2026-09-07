from collections.abc import AsyncIterator, Sequence
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import (
    APIConnectionError,
    AsyncOpenAI,
    AuthenticationError,
)
from openai.types.chat import ChatCompletionChunk

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import (
    ModelAuthenticationError,
    ModelConnectionError,
    ModelProtocolError,
    ModelRequest,
    ModelResponse,
    ModelResponseDone,
    ModelTextDelta,
    ModelUsage,
)
from minicode.core.tool_calls import ToolCall
from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
    openai_completion_stream_to_events,
    tool_spec_to_openai_tool,
)
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class EchoArguments(ToolArguments):
    text: str


def _make_text_chunk(
    content: str | None,
    *,
    finish_reason: (Literal["stop", "length"] | None) = None,
) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "delta": {
                        "content": content,
                    },
                    "finish_reason": finish_reason,
                    "index": 0,
                    "logprobs": None,
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion.chunk",
        }
    )


async def _iterate_chunks(
    chunks: Sequence[ChatCompletionChunk],
) -> AsyncIterator[ChatCompletionChunk]:
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_openai_stream_converts_text_deltas() -> None:
    chunks = (
        _make_text_chunk("MINI"),
        _make_text_chunk("CODE"),
        _make_text_chunk(
            None,
            finish_reason="stop",
        ),
    )

    events = [
        event
        async for event in openai_completion_stream_to_events(_iterate_chunks(chunks))
    ]

    assert events == [
        ModelTextDelta(
            text="MINI",
        ),
        ModelTextDelta(
            text="CODE",
        ),
        ModelResponseDone(
            response=ModelResponse(
                content="MINICODE",
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_openai_stream_rejects_missing_finish_reason() -> None:
    chunks = (_make_text_chunk("PARTIAL"),)

    with pytest.raises(
        ModelProtocolError,
        match="model stream ended without a finish reason",
    ):
        [
            event
            async for event in openai_completion_stream_to_events(
                _iterate_chunks(chunks)
            )
        ]


def _make_tool_chunk(
    tool_calls: list[dict[str, object]] | None = None,
    *,
    finish_reason: Literal["tool_calls"] | None = None,
) -> ChatCompletionChunk:
    delta: dict[str, object] = {}

    if tool_calls is not None:
        delta["tool_calls"] = tool_calls

    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "delta": delta,
                    "finish_reason": finish_reason,
                    "index": 0,
                    "logprobs": None,
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion.chunk",
        }
    )


@pytest.mark.asyncio
async def test_openai_stream_converts_single_tool_call() -> None:
    chunks = (
        _make_tool_chunk(
            [
                {
                    "index": 0,
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": "",
                    },
                }
            ]
        ),
        _make_tool_chunk(
            [
                {
                    "index": 0,
                    "function": {
                        "arguments": '{"path":"README',
                    },
                }
            ]
        ),
        _make_tool_chunk(
            [
                {
                    "index": 0,
                    "function": {
                        "arguments": '.md"}',
                    },
                }
            ]
        ),
        _make_tool_chunk(
            finish_reason="tool_calls",
        ),
    )

    events = [
        event
        async for event in openai_completion_stream_to_events(_iterate_chunks(chunks))
    ]

    assert events == [
        ModelResponseDone(
            response=ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        call_id="call_001",
                        name="read_file",
                        arguments={
                            "path": "README.md",
                        },
                    ),
                ),
            ),
        )
    ]


@pytest.mark.asyncio
async def test_openai_stream_rejects_length_truncation() -> None:
    chunks = (
        _make_text_chunk("PARTIAL"),
        _make_text_chunk(
            None,
            finish_reason="length",
        ),
    )

    with pytest.raises(
        ModelProtocolError,
        match="model stream did not complete: length",
    ):
        [
            event
            async for event in openai_completion_stream_to_events(
                _iterate_chunks(chunks)
            )
        ]


@pytest.mark.asyncio
async def test_openai_stream_converts_multiple_tool_calls_in_index_order() -> None:
    chunks = (
        _make_tool_chunk(
            [
                {
                    "index": 1,
                    "id": "call_002",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"pyproject'),
                    },
                },
                {
                    "index": 0,
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"README'),
                    },
                },
            ]
        ),
        _make_tool_chunk(
            [
                {
                    "index": 0,
                    "function": {
                        "arguments": '.md"}',
                    },
                },
                {
                    "index": 1,
                    "function": {
                        "arguments": '.toml"}',
                    },
                },
            ]
        ),
        _make_tool_chunk(
            finish_reason="tool_calls",
        ),
    )

    events = [
        event
        async for event in openai_completion_stream_to_events(_iterate_chunks(chunks))
    ]

    assert events == [
        ModelResponseDone(
            response=ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        call_id="call_001",
                        name="read_file",
                        arguments={
                            "path": "README.md",
                        },
                    ),
                    ToolCall(
                        call_id="call_002",
                        name="read_file",
                        arguments={
                            "path": "pyproject.toml",
                        },
                    ),
                ),
            ),
        )
    ]


@pytest.mark.asyncio
async def test_openai_compatible_model_streams_text_request() -> None:
    chunks = (
        _make_text_chunk("MINI"),
        _make_text_chunk("CODE"),
        _make_text_chunk(
            None,
            finish_reason="stop",
        ),
    )

    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=_iterate_chunks(chunks),
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    events = [event async for event in model.stream(request)]

    assert events == [
        ModelTextDelta(
            text="MINI",
        ),
        ModelTextDelta(
            text="CODE",
        ),
        ModelResponseDone(
            response=ModelResponse(
                content="MINICODE",
            ),
        ),
    ]
    create_completion.assert_awaited_once_with(
        model="qwen3.7-flash-2026-07-15",
        messages=[
            {
                "role": "user",
                "content": "Complete the task.",
            }
        ],
        stream=True,
        stream_options={
            "include_usage": True,
        },
    )


@pytest.mark.asyncio
async def test_openai_stream_translates_authentication_error() -> None:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 401
    response.headers = {}

    authentication_error = AuthenticationError(
        "Invalid API key.",
        response=response,
        body=None,
    )

    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=authentication_error,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    with pytest.raises(
        ModelAuthenticationError,
        match="model authentication failed",
    ) as exc_info:
        [event async for event in model.stream(request)]

    assert exc_info.value.__cause__ is (authentication_error)


async def _iterate_chunks_then_raise(
    chunks: Sequence[ChatCompletionChunk],
    error: Exception,
) -> AsyncIterator[ChatCompletionChunk]:
    for chunk in chunks:
        yield chunk

    raise error


@pytest.mark.asyncio
async def test_openai_stream_translates_connection_error_during_iteration() -> None:
    connection_error = APIConnectionError(
        message="Connection failed.",
        request=MagicMock(),
    )
    chunks = (_make_text_chunk("PARTIAL"),)

    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=_iterate_chunks_then_raise(
            chunks,
            connection_error,
        ),
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    events = model.stream(request)

    first_event = await anext(events)

    assert first_event == ModelTextDelta(
        text="PARTIAL",
    )

    with pytest.raises(
        ModelConnectionError,
        match="model service connection failed",
    ) as exc_info:
        await anext(events)

    assert exc_info.value.__cause__ is (connection_error)


@pytest.mark.asyncio
async def test_openai_compatible_model_streams_with_tools_and_extra_body() -> None:
    chunks = (
        _make_text_chunk(
            "Done.",
        ),
        _make_text_chunk(
            None,
            finish_reason="stop",
        ),
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=_iterate_chunks(chunks),
    )
    client.chat.completions.create = create_completion

    tool_spec = ToolSpec(
        name="echo",
        description="Return the supplied text.",
        arguments_type=EchoArguments,
    )
    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
        extra_body={
            "enable_thinking": False,
        },
    )
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Echo hello.",
            ),
        ),
        tool_specs=(tool_spec,),
    )

    events = [event async for event in model.stream(request)]

    assert events == [
        ModelTextDelta(
            text="Done.",
        ),
        ModelResponseDone(
            response=ModelResponse(
                content="Done.",
            ),
        ),
    ]
    create_completion.assert_awaited_once_with(
        model="qwen3.7-flash-2026-07-15",
        messages=[
            {
                "role": "user",
                "content": "Echo hello.",
            }
        ],
        tools=[tool_spec_to_openai_tool(tool_spec)],
        stream=True,
        stream_options={
            "include_usage": True,
        },
        extra_body={
            "enable_thinking": False,
        },
    )


def _make_usage_chunk(
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion.chunk",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": (completion_tokens),
                "total_tokens": (prompt_tokens + completion_tokens),
            },
        }
    )


@pytest.mark.asyncio
async def test_openai_stream_converts_usage() -> None:
    chunks = (
        _make_text_chunk("MINICODE"),
        _make_text_chunk(
            None,
            finish_reason="stop",
        ),
        _make_usage_chunk(
            prompt_tokens=12,
            completion_tokens=5,
        ),
    )

    events = [
        event
        async for event in openai_completion_stream_to_events(_iterate_chunks(chunks))
    ]

    assert events == [
        ModelTextDelta(
            text="MINICODE",
        ),
        ModelResponseDone(
            response=ModelResponse(
                content="MINICODE",
                usage=ModelUsage(
                    input_tokens=12,
                    output_tokens=5,
                ),
            ),
        ),
    ]
