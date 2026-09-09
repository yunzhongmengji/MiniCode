from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import (
    APIConnectionError,
    AsyncOpenAI,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletion

from minicode.core.messages import Message, MessageRole
from minicode.core.model import (
    ModelAccessDeniedError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelProtocolError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelServiceError,
    ModelUsage,
)
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.openai_compatible import (
    OpenAICompatibleModel,
    conversation_to_openai_messages,
    model_request_to_openai_messages,
    openai_completion_to_model_response,
    tool_spec_to_openai_tool,
)
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec


class EchoArguments(ToolArguments):
    text: str


def test_tool_spec_converts_to_openai_function_tool() -> None:
    tool_spec = ToolSpec(
        name="echo",
        description="Return the supplied text.",
        arguments_type=EchoArguments,
    )

    openai_tool = tool_spec_to_openai_tool(tool_spec)

    assert openai_tool == {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Return the supplied text.",
            "parameters": EchoArguments.model_json_schema(),
        },
    }


def test_model_request_adds_instructions_before_conversation() -> None:
    user_message = Message(
        role=MessageRole.USER,
        content="Fix the failing test.",
    )
    request = ModelRequest(
        conversation=(user_message,),
        instructions=(("# Loaded Skills\n\nRun the smallest failing test first."),),
    )

    messages = model_request_to_openai_messages(request)

    assert messages == [
        {
            "role": "system",
            "content": ("# Loaded Skills\n\nRun the smallest failing test first."),
        },
        {
            "role": "user",
            "content": "Fix the failing test.",
        },
    ]
    assert request.conversation == (user_message,)


def test_conversation_converts_plain_messages() -> None:
    conversation = (
        Message(
            role=MessageRole.SYSTEM,
            content="You are a coding agent.",
        ),
        Message(
            role=MessageRole.USER,
            content="Read README.md",
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="I will inspect the file.",
        ),
    )

    openai_messages = conversation_to_openai_messages(conversation)

    assert openai_messages == [
        {
            "role": "system",
            "content": "You are a coding agent.",
        },
        {
            "role": "user",
            "content": "Read README.md",
        },
        {
            "role": "assistant",
            "content": "I will inspect the file.",
        },
    ]


def test_conversation_converts_tool_result() -> None:
    tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )

    openai_messages = conversation_to_openai_messages((tool_result,))

    assert openai_messages == [
        {
            "role": "tool",
            "tool_call_id": "call_001",
            "content": "README contents.",
        }
    ]


def test_conversation_marks_tool_result_error() -> None:
    tool_result = ToolResult(
        call_id="call_001",
        output="README.md was not found.",
        is_error=True,
    )

    openai_messages = conversation_to_openai_messages((tool_result,))

    assert openai_messages == [
        {
            "role": "tool",
            "tool_call_id": "call_001",
            "content": ("Tool execution failed: README.md was not found."),
        }
    ]


def test_conversation_converts_single_tool_call() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )

    openai_messages = conversation_to_openai_messages((tool_call,))

    assert openai_messages == [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"README.md"}'),
                    },
                }
            ],
        }
    ]


def test_conversation_converts_nested_tool_arguments() -> None:
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "options": {
                "mode": "safe",
                "lines": [1, 2],
            },
        },
    )

    openai_messages = conversation_to_openai_messages((tool_call,))

    assert openai_messages[0]["tool_calls"][0]["function"]["arguments"] == (
        '{"options":{"lines":[1,2],"mode":"safe"}}'
    )


def test_conversation_groups_consecutive_tool_calls() -> None:
    first_tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    second_tool_call = ToolCall(
        call_id="call_002",
        name="read_file",
        arguments={"path": "pyproject.toml"},
    )

    openai_messages = conversation_to_openai_messages(
        (
            first_tool_call,
            second_tool_call,
        )
    )

    assert openai_messages == [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"README.md"}'),
                    },
                },
                {
                    "id": "call_002",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"pyproject.toml"}'),
                    },
                },
            ],
        }
    ]


def test_conversation_merges_assistant_text_with_tool_calls() -> None:
    assistant_message = Message(
        role=MessageRole.ASSISTANT,
        content="I will read the file.",
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )

    openai_messages = conversation_to_openai_messages(
        (
            assistant_message,
            tool_call,
        )
    )

    assert openai_messages == [
        {
            "role": "assistant",
            "content": "I will read the file.",
            "tool_calls": [
                {
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": ('{"path":"README.md"}'),
                    },
                }
            ],
        }
    ]


def test_openai_completion_converts_text_response() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": "Task completed.",
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    response = openai_completion_to_model_response(completion)

    assert response == ModelResponse(
        content="Task completed.",
    )


def test_openai_completion_converts_tool_call() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": ('{"path":"README.md"}'),
                                },
                            }
                        ],
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    response = openai_completion_to_model_response(completion)

    assert response == ModelResponse(
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
    )


def test_openai_completion_rejects_invalid_tool_arguments_json() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":',
                                },
                            }
                        ],
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    with pytest.raises(
        ModelProtocolError,
        match="model returned invalid JSON tool arguments",
    ):
        openai_completion_to_model_response(completion)


def test_openai_completion_rejects_non_object_tool_arguments() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '["README.md"]',
                                },
                            }
                        ],
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    with pytest.raises(
        ModelProtocolError,
        match="model tool-call arguments must decode to an object",
    ):
        openai_completion_to_model_response(completion)


def test_openai_completion_rejects_missing_choices() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    with pytest.raises(
        ModelProtocolError,
        match="model returned no choices",
    ):
        openai_completion_to_model_response(completion)


def test_openai_completion_rejects_unsupported_tool_call_type() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "custom",
                                "custom": {
                                    "name": "shell",
                                    "input": "pwd",
                                },
                            }
                        ],
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    with pytest.raises(
        ModelProtocolError,
        match="model returned unsupported tool-call type",
    ):
        openai_completion_to_model_response(completion)


def test_openai_completion_rejects_blank_tool_name() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "function",
                                "function": {
                                    "name": "",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    with pytest.raises(
        ModelProtocolError,
        match="model returned invalid tool call",
    ):
        openai_completion_to_model_response(completion)


@pytest.mark.asyncio
async def test_openai_compatible_model_completes_text_request() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": "Task completed.",
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=completion,
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

    response = await model.complete(request)

    assert response == ModelResponse(
        content="Task completed.",
    )
    create_completion.assert_awaited_once_with(
        model="qwen3.7-flash-2026-07-15",
        messages=[
            {
                "role": "user",
                "content": "Complete the task.",
            }
        ],
    )


@pytest.mark.asyncio
async def test_openai_compatible_model_provides_tools() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": "Task completed.",
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=completion,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    tool_spec = ToolSpec(
        name="echo",
        description="Return the supplied text.",
        arguments_type=EchoArguments,
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

    response = await model.complete(request)

    assert response == ModelResponse(
        content="Task completed.",
    )
    create_completion.assert_awaited_once_with(
        model="qwen3.7-flash-2026-07-15",
        messages=[
            {
                "role": "user",
                "content": "Echo hello.",
            }
        ],
        tools=[tool_spec_to_openai_tool(tool_spec)],
    )


@pytest.mark.parametrize(
    "model_name",
    [
        "",
        " ",
        "\t",
    ],
)
def test_openai_compatible_model_rejects_blank_model_name(
    model_name: str,
) -> None:
    client = MagicMock(
        spec=AsyncOpenAI,
    )

    with pytest.raises(
        ValueError,
        match="model must not be blank",
    ):
        OpenAICompatibleModel(
            client=client,
            model=model_name,
        )


@pytest.mark.parametrize(
    "model_name",
    [
        123,
        None,
        True,
    ],
)
def test_openai_compatible_model_rejects_non_string_model_name(
    model_name: object,
) -> None:
    client = MagicMock(
        spec=AsyncOpenAI,
    )

    with pytest.raises(
        TypeError,
        match="model must be a string",
    ):
        OpenAICompatibleModel(
            client=client,
            model=model_name,
        )


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_authentication_error() -> None:
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
        await model.complete(request)

    assert exc_info.value.__cause__ is authentication_error


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_rate_limit_error() -> None:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 429
    response.headers = {}

    rate_limit_error = RateLimitError(
        "Rate limit exceeded.",
        response=response,
        body=None,
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=rate_limit_error,
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
        ModelRateLimitError,
        match="model rate limit exceeded",
    ) as exc_info:
        await model.complete(request)

    assert exc_info.value.__cause__ is rate_limit_error


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_connection_error() -> None:
    http_request = MagicMock()
    connection_error = APIConnectionError(
        message="Connection failed.",
        request=http_request,
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=connection_error,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    model_request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    with pytest.raises(
        ModelConnectionError,
        match="model service connection failed",
    ) as exc_info:
        await model.complete(model_request)

    assert exc_info.value.__cause__ is connection_error


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_free_quota_error() -> None:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 403
    response.headers = {}

    quota_error = PermissionDeniedError(
        "The free tier of the model has been exhausted.",
        response=response,
        body={
            "code": "AllocationQuota.FreeTierOnly",
            "message": ("The free tier of the model has been exhausted."),
            "type": "invalid_request_error",
        },
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=quota_error,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    model_request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    with pytest.raises(
        ModelQuotaExceededError,
        match="model free quota exhausted",
    ) as exc_info:
        await model.complete(model_request)

    assert exc_info.value.__cause__ is quota_error


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_access_denied_error() -> None:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 403
    response.headers = {}

    access_error = PermissionDeniedError(
        "Model access denied.",
        response=response,
        body={
            "code": "Model.AccessDenied",
            "message": "Model access denied.",
            "type": "invalid_request_error",
        },
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=access_error,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    model_request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    with pytest.raises(
        ModelAccessDeniedError,
        match="model access denied",
    ) as exc_info:
        await model.complete(model_request)

    assert exc_info.value.__cause__ is access_error


@pytest.mark.asyncio
async def test_openai_compatible_model_translates_service_error() -> None:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 500
    response.headers = {}

    service_error = InternalServerError(
        "The server had an error.",
        response=response,
        body={
            "code": "internal_server_error",
            "message": "The server had an error.",
            "type": "server_error",
        },
    )
    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        side_effect=service_error,
    )
    client.chat.completions.create = create_completion

    model = OpenAICompatibleModel(
        client=client,
        model="qwen3.7-flash-2026-07-15",
    )
    model_request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Complete the task.",
            ),
        ),
    )

    with pytest.raises(
        ModelServiceError,
        match="model service request failed",
    ) as exc_info:
        await model.complete(model_request)

    assert exc_info.value.__cause__ is service_error


@pytest.mark.asyncio
async def test_openai_compatible_model_provides_extra_body() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": "Task completed.",
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
        }
    )

    client = MagicMock(
        spec=AsyncOpenAI,
    )
    create_completion = AsyncMock(
        return_value=completion,
    )
    client.chat.completions.create = create_completion

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
                content="Complete the task.",
            ),
        ),
    )

    response = await model.complete(request)

    assert response == ModelResponse(
        content="Task completed.",
    )
    create_completion.assert_awaited_once_with(
        model="qwen3.7-flash-2026-07-15",
        messages=[
            {
                "role": "user",
                "content": "Complete the task.",
            }
        ],
        extra_body={
            "enable_thinking": False,
        },
    )


@pytest.mark.parametrize(
    "extra_body",
    [
        [],
        "",
        b"",
    ],
)
def test_openai_compatible_model_rejects_invalid_extra_body(
    extra_body: object,
) -> None:
    client = MagicMock(
        spec=AsyncOpenAI,
    )

    with pytest.raises(
        TypeError,
        match="extra_body must be a mapping",
    ):
        OpenAICompatibleModel(
            client=client,
            model="qwen3.7-flash-2026-07-15",
            extra_body=extra_body,
        )


def test_openai_completion_converts_usage() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "role": "assistant",
                        "content": "Task completed.",
                    },
                }
            ],
            "created": 0,
            "model": "qwen3.7-flash-2026-07-15",
            "object": "chat.completion",
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        }
    )

    response = openai_completion_to_model_response(completion)

    assert response.usage == ModelUsage(
        input_tokens=12,
        output_tokens=5,
    )
