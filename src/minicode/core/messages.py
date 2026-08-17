"""Message types exchanged by MiniCode components."""

from dataclasses import dataclass
from enum import StrEnum


class MessageRole(StrEnum):
    """Allowed roles for messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class Message:
    """A message exchanged between Agent components."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        """Validate the message after initialization."""
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
