from dataclasses import FrozenInstanceError

import pytest

from minicode.core.messages import Message, MessageRole


def test_message_stores_role_and_content() -> None:
    message = Message(
        role=MessageRole.USER,
        content="修复测试",
    )

    assert message.role is MessageRole.USER
    assert message.content == "修复测试"


def test_message_cannot_be_modified_after_creation() -> None:
    message = Message(
        role=MessageRole.USER,
        content="修复测试",
    )

    with pytest.raises(FrozenInstanceError):
        message.content = "删除项目"


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(TypeError, match="role must be a MessageRole"):
        Message(
            role="uesr",
            content="修复测试",
        )


def test_message_rejects_invalid_content() -> None:
    with pytest.raises(TypeError, match="content must be a string"):
        Message(
            role=MessageRole.USER,
            content=123,
        )
