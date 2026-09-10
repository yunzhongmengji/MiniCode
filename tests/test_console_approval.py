import pytest

from minicode.console_approval import ConsoleToolApprover
from minicode.core.tool_calls import ToolCall


@pytest.mark.asyncio
async def test_console_approver_shows_exact_call_and_fails_closed() -> None:
    answers = iter(
        (
            " YES ",
            "anything else",
        )
    )
    prompts: list[str] = []

    def read_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    approver = ConsoleToolApprover(
        input_reader=read_input,
    )
    tool_call = ToolCall(
        call_id="call_edit",
        name="edit_file",
        arguments={
            "path": "计算器.py",
            "old_text": "left - right",
            "new_text": "left + right",
            "metadata": {
                "related_paths": [
                    "tests/test_计算器.py",
                ],
            },
        },
    )

    approved = await approver.request_approval(
        tool_call,
        reason="workspace changes require approval",
    )
    denied = await approver.request_approval(
        tool_call,
        reason="workspace changes require approval",
    )

    assert approved is True
    assert denied is False
    assert len(prompts) == 2
    assert "Tool: edit_file" in prompts[0]
    assert '"path": "计算器.py"' in prompts[0]
    assert ('"metadata": {"related_paths": ["tests/test_计算器.py"]}') in prompts[0]
    assert "workspace changes require approval" in prompts[0]
