import pytest

from minicode.console_approval import ConsoleToolApprover
from minicode.core.tool_calls import ToolCall


@pytest.mark.asyncio
async def test_console_approver_shows_exact_call_on_stderr_and_fails_closed(
    capsys,
) -> None:
    answers = iter(
        (
            " YES ",
            "anything else",
        )
    )

    def read_input() -> str:
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
    captured = capsys.readouterr()

    assert approved is True
    assert denied is False
    assert captured.out == ""
    assert captured.err.count("Tool approval required") == 2
    assert "Tool: edit_file" in captured.err
    assert '"path": "计算器.py"' in captured.err
    assert '"metadata": {"related_paths": ["tests/test_计算器.py"]}' in captured.err
    assert "workspace changes require approval" in captured.err
