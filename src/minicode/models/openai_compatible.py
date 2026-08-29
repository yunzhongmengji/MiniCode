"""OpenAI-compatible model adapter and payload conversion."""

import json
from collections.abc import Mapping, Sequence
from typing import TypedDict

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
)

from minicode.core.conversation import ConversationItem
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
)
from minicode.core.tool_calls import (
    JsonValue,
    ToolCall,
    ToolResult,
)
from minicode.tools.spec import ToolSpec


class _CompletionCreateOptions(TypedDict, total=False):
    """Optional keyword arguments for an SDK completion request."""

    extra_body: object


def tool_spec_to_openai_tool(
    tool_spec: ToolSpec,
) -> ChatCompletionFunctionToolParam:
    """Convert MiniCode tool metadata into an OpenAI function tool."""
    return {
        "type": "function",
        "function": {
            "name": tool_spec.name,
            "description": tool_spec.description,
            "parameters": (tool_spec.arguments_type.model_json_schema()),
        },
    }


def _to_json_compatible_value(
    value: JsonValue,
) -> object:
    """Convert frozen JSON values into built-in JSON containers."""
    if isinstance(value, Mapping):
        return {key: _to_json_compatible_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_json_compatible_value(item) for item in value]

    return value


def _tool_call_to_openai_tool_call(
    tool_call: ToolCall,
) -> ChatCompletionMessageFunctionToolCallParam:
    """Convert one MiniCode tool call into OpenAI history format."""
    arguments_json = json.dumps(
        _to_json_compatible_value(tool_call.arguments),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return {
        "id": tool_call.call_id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": arguments_json,
        },
    }


def _append_pending_assistant_message(
    messages: list[ChatCompletionMessageParam],
    content: str | None,
    tool_calls: list[ChatCompletionMessageFunctionToolCallParam],
) -> None:
    """Append a pending assistant message when it has content."""
    if content is None and not tool_calls:
        return

    assistant_message: ChatCompletionAssistantMessageParam = {
        "role": "assistant",
    }

    if content is not None:
        assistant_message["content"] = content

    if tool_calls:
        assistant_message["tool_calls"] = tool_calls

    messages.append(assistant_message)


def conversation_to_openai_messages(
    conversation: Sequence[ConversationItem],
) -> list[ChatCompletionMessageParam]:
    """Convert MiniCode conversation items into OpenAI messages."""
    messages: list[ChatCompletionMessageParam] = []

    pending_assistant_content: str | None = None
    pending_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []

    for item in conversation:
        if isinstance(item, ToolCall):
            pending_tool_calls.append(_tool_call_to_openai_tool_call(item))
            continue

        if isinstance(item, Message) and item.role is MessageRole.ASSISTANT:
            _append_pending_assistant_message(
                messages,
                pending_assistant_content,
                pending_tool_calls,
            )
            pending_assistant_content = item.content
            pending_tool_calls = []
            continue

        _append_pending_assistant_message(
            messages,
            pending_assistant_content,
            pending_tool_calls,
        )
        pending_assistant_content = None
        pending_tool_calls = []

        if isinstance(item, ToolResult):
            content = item.output

            if item.is_error:
                content = f"Tool execution failed: {item.output}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": content,
                }
            )
            continue

        if not isinstance(item, Message):
            raise NotImplementedError(
                "tool conversation conversion is not implemented yet"
            )

        if item.role is MessageRole.SYSTEM:
            messages.append(
                {
                    "role": "system",
                    "content": item.content,
                }
            )
        elif item.role is MessageRole.USER:
            messages.append(
                {
                    "role": "user",
                    "content": item.content,
                }
            )
        else:
            raise ValueError("tool messages require a structured ToolResult")

    _append_pending_assistant_message(
        messages,
        pending_assistant_content,
        pending_tool_calls,
    )

    return messages


def openai_completion_to_model_response(
    completion: ChatCompletion,
) -> ModelResponse:
    """Convert an OpenAI chat completion into a MiniCode response."""
    if not completion.choices:
        raise ModelProtocolError("model returned no choices")

    message = completion.choices[0].message
    content = message.content or ""
    tool_calls: list[ToolCall] = []

    for openai_tool_call in message.tool_calls or []:
        if openai_tool_call.type != "function":
            raise ModelProtocolError("model returned unsupported tool-call type")

        try:
            arguments = json.loads(openai_tool_call.function.arguments)
        except json.JSONDecodeError as error:
            raise ModelProtocolError(
                "model returned invalid JSON tool arguments"
            ) from error

        if not isinstance(arguments, Mapping):
            raise ModelProtocolError(
                "model tool-call arguments must decode to an object"
            )

        try:
            tool_call = ToolCall(
                call_id=openai_tool_call.id,
                name=openai_tool_call.function.name,
                arguments=arguments,
            )
        except (TypeError, ValueError) as error:
            raise ModelProtocolError("model returned invalid tool call") from error

        tool_calls.append(tool_call)

    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
    )


class OpenAICompatibleModel:
    """Call an OpenAI-compatible chat completion API."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        extra_body: Mapping[str, object] | None = None,
    ) -> None:
        if not isinstance(model, str):
            raise TypeError("model must be a string")

        if not model.strip():
            raise ValueError("model must not be blank")
        if extra_body is not None and not isinstance(
            extra_body,
            Mapping,
        ):
            raise TypeError("extra_body must be a mapping")

        self._client = client
        self._model = model
        self._extra_body = dict(extra_body) if extra_body is not None else None

    async def complete(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """Complete a normalized MiniCode model request."""
        messages = conversation_to_openai_messages(request.conversation)
        tools = [
            tool_spec_to_openai_tool(tool_spec) for tool_spec in request.tool_specs
        ]
        create_options: _CompletionCreateOptions = {}

        if self._extra_body is not None:
            create_options["extra_body"] = self._extra_body

        try:
            if tools:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    **create_options,
                )
            else:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    **create_options,
                )
        except AuthenticationError as error:
            raise ModelAuthenticationError("model authentication failed") from error
        except PermissionDeniedError as error:
            if error.code == "AllocationQuota.FreeTierOnly":
                raise ModelQuotaExceededError("model free quota exhausted") from error

            raise ModelAccessDeniedError("model access denied") from error
        except RateLimitError as error:
            raise ModelRateLimitError("model rate limit exceeded") from error
        except APIConnectionError as error:
            raise ModelConnectionError("model service connection failed") from error
        except APIStatusError as error:
            raise ModelServiceError("model service request failed") from error

        return openai_completion_to_model_response(completion)
