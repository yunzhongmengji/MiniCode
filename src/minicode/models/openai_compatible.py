"""OpenAI-compatible model adapter built on Pydantic v2 schemas."""

from __future__ import annotations

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

from minicode.models.base import (
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
from minicode.schemas.messages import (
    HistoryEntry,
    MessageRecord,
    MessageRole,
    TokenUsage,
    ToolCallRecord,
    ToolResultRecord,
)
from minicode.tools.spec import ToolSpec


class _CompletionCreateOptions(TypedDict, total=False):
    extra_body: object
    max_completion_tokens: int


def tool_spec_to_openai_tool(
    tool_spec: ToolSpec,
) -> ChatCompletionFunctionToolParam:
    """Convert MiniCode ToolSpec into an OpenAI function tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool_spec.name,
            "description": tool_spec.description,
            "parameters": tool_spec.arguments_type.model_json_schema(),
        },
    }


def _append_pending_assistant(
    messages: list[ChatCompletionMessageParam],
    content: str | None,
    tool_calls: list[ChatCompletionMessageFunctionToolCallParam],
) -> None:
    if content is None and not tool_calls:
        return
    assistant_msg: ChatCompletionAssistantMessageParam = {"role": "assistant"}
    if content is not None:
        assistant_msg["content"] = content
    if tool_calls:
        assistant_msg["tool_calls"] = list(tool_calls)
    messages.append(assistant_msg)


def conversation_to_openai_messages(
    conversation: Sequence[HistoryEntry],
    *,
    instructions: Sequence[str] = (),
) -> list[ChatCompletionMessageParam]:
    """Translate MiniCode history entries and system instructions into OpenAI messages."""
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": instruction} for instruction in instructions
    ]
    pending_content: str | None = None
    pending_calls: list[ChatCompletionMessageFunctionToolCallParam] = []

    for item in conversation:
        if isinstance(item, MessageRecord):
            if item.role is MessageRole.ASSISTANT:
                _append_pending_assistant(messages, pending_content, pending_calls)
                pending_content = item.content
                pending_calls = []
                continue
            _append_pending_assistant(messages, pending_content, pending_calls)
            pending_content = None
            pending_calls = []
            if item.role is MessageRole.SYSTEM:
                messages.append({"role": "system", "content": item.content})
            else:
                messages.append({"role": "user", "content": item.content})
        elif isinstance(item, ToolCallRecord):
            pending_calls.append(
                {
                    "id": item.call_id,
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "arguments": json.dumps(
                            item.arguments,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                }
            )
        elif isinstance(item, ToolResultRecord):
            _append_pending_assistant(messages, pending_content, pending_calls)
            pending_content = None
            pending_calls = []
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": item.output,
                }
            )

    _append_pending_assistant(messages, pending_content, pending_calls)
    return messages


def _parse_completion(completion: ChatCompletion) -> ModelResponse:
    if not completion.choices:
        raise ModelProtocolError("provider returned completion with no choices")

    message = completion.choices[0].message
    content = message.content or ""
    tool_calls: list[ToolCallRecord] = []

    for raw_call in message.tool_calls or ():
        if raw_call.type != "function":
            continue
        try:
            decoded_args = json.loads(raw_call.function.arguments or "{}")
        except json.JSONDecodeError as error:
            raise ModelProtocolError(
                "model returned invalid JSON tool arguments"
            ) from error
        if not isinstance(decoded_args, Mapping):
            raise ModelProtocolError("model tool arguments must decode to an object")
        tool_calls.append(
            ToolCallRecord(
                call_id=raw_call.id,
                name=raw_call.function.name,
                arguments=dict(decoded_args),
            )
        )

    usage: TokenUsage | None = None
    if completion.usage is not None:
        usage = TokenUsage(
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )

    return ModelResponse(
        content=content,
        tool_calls=tuple(tool_calls),
        usage=usage,
    )


def _translate_sdk_error(error: Exception) -> ModelError:
    if isinstance(error, AuthenticationError):
        return ModelAuthenticationError(str(error))
    if isinstance(error, PermissionDeniedError):
        return ModelAccessDeniedError(str(error))
    if isinstance(error, RateLimitError):
        return ModelRateLimitError(str(error))
    if isinstance(error, APIConnectionError):
        return ModelConnectionError(str(error))
    if isinstance(error, APIStatusError):
        return ModelServiceError(f"provider HTTP {error.status_code}: {error.message}")
    return ModelServiceError(str(error))


class OpenAICompatibleModel:
    """Async OpenAI-compatible Chat Completions adapter."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        extra_body: Mapping[str, object] | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        self._client = client
        self._model = model
        self._extra_body = dict(extra_body) if extra_body is not None else None
        self._max_output_tokens = max_output_tokens

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Send one provider-neutral request and return a validated ModelResponse."""
        messages = conversation_to_openai_messages(
            request.conversation,
            instructions=request.instructions,
        )
        tools = [tool_spec_to_openai_tool(spec) for spec in request.tool_specs]
        options: _CompletionCreateOptions = {}
        if self._extra_body is not None:
            options["extra_body"] = self._extra_body
        if self._max_output_tokens is not None:
            options["max_completion_tokens"] = self._max_output_tokens

        try:
            if tools:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    **options,
                )
            else:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    **options,
                )
        except (
            AuthenticationError,
            PermissionDeniedError,
            RateLimitError,
            APIConnectionError,
            APIStatusError,
        ) as error:
            raise _translate_sdk_error(error) from error

        return _parse_completion(completion)
