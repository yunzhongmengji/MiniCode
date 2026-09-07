"""OpenAI-compatible model adapter and payload conversion."""

import json
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
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
    ChatCompletionChunk,
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
    ModelError,
    ModelProtocolError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelResponseDone,
    ModelServiceError,
    ModelStreamEvent,
    ModelTextDelta,
    ModelUsage,
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


@dataclass(slots=True)
class _ToolCallAccumulator:
    """Collect fragments for one streamed tool call."""

    call_id: str | None = None
    name: str | None = None
    tool_type: str | None = None
    argument_parts: list[str] = field(
        default_factory=list,
    )


def _tool_call_from_json(
    *,
    call_id: str,
    name: str,
    arguments_json: str,
) -> ToolCall:
    """Build a validated MiniCode tool call from provider fields."""
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as error:
        raise ModelProtocolError(
            "model returned invalid JSON tool arguments"
        ) from error

    if not isinstance(arguments, Mapping):
        raise ModelProtocolError("model tool-call arguments must decode to an object")

    try:
        return ToolCall(
            call_id=call_id,
            name=name,
            arguments=arguments,
        )
    except (TypeError, ValueError) as error:
        raise ModelProtocolError("model returned invalid tool call") from error


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

        tool_calls.append(
            _tool_call_from_json(
                call_id=openai_tool_call.id,
                name=openai_tool_call.function.name,
                arguments_json=(openai_tool_call.function.arguments),
            )
        )

    usage = None

    if completion.usage is not None:
        usage = ModelUsage(
            input_tokens=(completion.usage.prompt_tokens),
            output_tokens=(completion.usage.completion_tokens),
        )

    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
    )


async def openai_completion_stream_to_events(
    chunks: AsyncIterable[ChatCompletionChunk],
) -> AsyncIterator[ModelStreamEvent]:
    """Convert OpenAI completion chunks into MiniCode stream events."""
    content_parts: list[str] = []
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    tool_call_accumulators: dict[
        int,
        _ToolCallAccumulator,
    ] = {}

    async for chunk in chunks:
        if chunk.usage is not None:
            usage = ModelUsage(
                input_tokens=(chunk.usage.prompt_tokens),
                output_tokens=(chunk.usage.completion_tokens),
            )

        if not chunk.choices:
            continue

        choice = chunk.choices[0]

        if choice.finish_reason is not None:
            finish_reason = choice.finish_reason

        for tool_call_delta in choice.delta.tool_calls or []:
            accumulator = tool_call_accumulators.get(tool_call_delta.index)

            if accumulator is None:
                accumulator = _ToolCallAccumulator()
                tool_call_accumulators[tool_call_delta.index] = accumulator

            if tool_call_delta.id is not None:
                accumulator.call_id = tool_call_delta.id

            if tool_call_delta.type is not None:
                accumulator.tool_type = tool_call_delta.type

            if tool_call_delta.function is not None:
                if tool_call_delta.function.name is not None:
                    accumulator.name = tool_call_delta.function.name

                if tool_call_delta.function.arguments is not None:
                    accumulator.argument_parts.append(
                        tool_call_delta.function.arguments
                    )

        content = choice.delta.content

        if content is None or content == "":
            continue

        content_parts.append(content)

        yield ModelTextDelta(
            text=content,
        )

    if finish_reason is None:
        raise ModelProtocolError("model stream ended without a finish reason")

    if finish_reason not in (
        "stop",
        "tool_calls",
    ):
        raise ModelProtocolError(f"model stream did not complete: {finish_reason}")

    tool_calls: list[ToolCall] = []

    for index in sorted(tool_call_accumulators):
        accumulator = tool_call_accumulators[index]

        if accumulator.tool_type != "function":
            raise ModelProtocolError("model returned unsupported tool-call type")

        if accumulator.call_id is None or accumulator.name is None:
            raise ModelProtocolError("model returned invalid tool call")

        tool_calls.append(
            _tool_call_from_json(
                call_id=accumulator.call_id,
                name=accumulator.name,
                arguments_json="".join(accumulator.argument_parts),
            )
        )

    complete_content = "".join(content_parts)

    yield ModelResponseDone(
        response=ModelResponse(
            content=complete_content,
            tool_calls=tool_calls,
            usage=usage,
        ),
    )


def _translate_openai_error(
    error: APIConnectionError | APIStatusError,
) -> ModelError:
    """Translate an OpenAI SDK error into a provider-neutral model error."""
    if isinstance(error, AuthenticationError):
        return ModelAuthenticationError("model authentication failed")

    if isinstance(error, PermissionDeniedError):
        if error.code == "AllocationQuota.FreeTierOnly":
            return ModelQuotaExceededError("model free quota exhausted")

        return ModelAccessDeniedError("model access denied")

    if isinstance(error, RateLimitError):
        return ModelRateLimitError("model rate limit exceeded")

    if isinstance(error, APIConnectionError):
        return ModelConnectionError("model service connection failed")

    return ModelServiceError("model service request failed")


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
        except (
            APIConnectionError,
            APIStatusError,
        ) as error:
            raise _translate_openai_error(error) from error

        return openai_completion_to_model_response(completion)

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Stream a normalized MiniCode model request."""
        messages = conversation_to_openai_messages(request.conversation)
        tools = [
            tool_spec_to_openai_tool(tool_spec) for tool_spec in request.tool_specs
        ]
        create_options: _CompletionCreateOptions = {}

        if self._extra_body is not None:
            create_options["extra_body"] = self._extra_body

        try:
            if tools:
                chunks = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    stream=True,
                    stream_options={
                        "include_usage": True,
                    },
                    **create_options,
                )
            else:
                chunks = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    stream=True,
                    stream_options={
                        "include_usage": True,
                    },
                    **create_options,
                )

            async for event in openai_completion_stream_to_events(chunks):
                yield event

        except (
            APIConnectionError,
            APIStatusError,
        ) as error:
            raise _translate_openai_error(error) from error
