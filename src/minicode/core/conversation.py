"""Provider-neutral items stored in conversation history."""

from minicode.core.messages import Message
from minicode.core.tool_calls import ToolCall, ToolResult

type ConversationItem = Message | ToolCall | ToolResult
