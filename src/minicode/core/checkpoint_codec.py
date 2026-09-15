"""JSON encoding for durable query-loop checkpoints."""

import json
from collections.abc import Mapping
from typing import cast

from minicode.core.checkpoints import RunCheckpoint
from minicode.core.conversation import ConversationItem
from minicode.core.messages import Message, MessageRole
from minicode.core.tool_calls import JsonValue, ToolCall, ToolResult

_SCHEMA_VERSION = 2


def checkpoint_to_json(checkpoint: RunCheckpoint) -> str:
    """Encode one validated checkpoint as stable JSON text."""
    if not isinstance(checkpoint, RunCheckpoint):
        raise TypeError("checkpoint must be a RunCheckpoint")

    document: dict[str, JsonValue] = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": checkpoint.run_id,
        "message_history": tuple(
            _encode_history_item(item) for item in checkpoint.message_history
        ),
        "turns_used": checkpoint.turns_used,
        "tool_calls_used": checkpoint.tool_calls_used,
        "is_completed": checkpoint.is_completed,
    }
    return json.dumps(
        _plain_json_value(document),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def checkpoint_from_json(document: str) -> RunCheckpoint:
    """Decode JSON text into one validated checkpoint."""
    decoded: object = json.loads(document)

    if not isinstance(decoded, Mapping):
        raise TypeError("checkpoint document must be an object")

    source = cast(Mapping[str, object], decoded)
    schema_version = _required_integer(source, "schema_version")

    if schema_version not in (1, _SCHEMA_VERSION):
        raise ValueError(f"unsupported checkpoint schema {schema_version}")

    history = _required_list(source, "message_history")
    return RunCheckpoint(
        run_id=_required_string(source, "run_id"),
        message_history=tuple(_decode_history_item(item) for item in history),
        turns_used=_required_integer(source, "turns_used"),
        tool_calls_used=_required_integer(source, "tool_calls_used"),
        is_completed=(
            _required_boolean(source, "is_completed") if schema_version == 2 else False
        ),
    )


def _encode_history_item(item: ConversationItem) -> dict[str, JsonValue]:
    if isinstance(item, Message):
        return {
            "type": "message",
            "role": item.role.value,
            "content": item.content,
        }

    if isinstance(item, ToolCall):
        return {
            "type": "tool_call",
            "call_id": item.call_id,
            "name": item.name,
            "arguments": item.arguments,
        }

    if isinstance(item, ToolResult):
        return {
            "type": "tool_result",
            "call_id": item.call_id,
            "output": item.output,
            "is_error": item.is_error,
        }

    raise TypeError("unsupported checkpoint history item")


def _decode_history_item(value: object) -> ConversationItem:
    if not isinstance(value, Mapping):
        raise TypeError("checkpoint history items must be objects")

    source = cast(Mapping[str, object], value)
    item_type = _required_string(source, "type")

    if item_type == "message":
        return Message(
            role=MessageRole(_required_string(source, "role")),
            content=_required_string(source, "content"),
        )

    if item_type == "tool_call":
        arguments = _required_mapping(source, "arguments")
        return ToolCall(
            call_id=_required_string(source, "call_id"),
            name=_required_string(source, "name"),
            arguments=cast(Mapping[str, JsonValue], arguments),
        )

    if item_type == "tool_result":
        return ToolResult(
            call_id=_required_string(source, "call_id"),
            output=_required_string(source, "output"),
            is_error=_required_boolean(source, "is_error"),
        )

    raise ValueError(f"unsupported checkpoint history item type: {item_type}")


def _plain_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _plain_json_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_plain_json_value(item) for item in value]

    return value


def _required_mapping(
    source: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = source.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")

    return cast(Mapping[str, object], value)


def _required_list(
    source: Mapping[str, object],
    key: str,
) -> list[object]:
    value = source.get(key)

    if not isinstance(value, list):
        raise TypeError(f"{key} must be an array")

    return cast(list[object], value)


def _required_string(
    source: Mapping[str, object],
    key: str,
) -> str:
    value = source.get(key)

    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")

    return value


def _required_integer(
    source: Mapping[str, object],
    key: str,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer")

    return value


def _required_boolean(
    source: Mapping[str, object],
    key: str,
) -> bool:
    value = source.get(key)

    if type(value) is not bool:
        raise TypeError(f"{key} must be a boolean")

    return value
