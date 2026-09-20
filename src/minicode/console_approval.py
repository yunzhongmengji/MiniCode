"""Interactive terminal approval for policy-gated tool calls."""

import asyncio
import json
import sys
from collections.abc import Callable

from minicode.core.tool_calls import ToolCall, to_plain_json


class ConsoleToolApprover:
    """Ask the terminal user to approve one exact tool call."""

    def __init__(
        self,
        *,
        input_reader: Callable[[], str] = input,
    ) -> None:
        self._input_reader = input_reader

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        """Approve only an explicit y or yes response."""
        rendered_arguments = json.dumps(
            to_plain_json(tool_call.arguments),
            ensure_ascii=False,
            sort_keys=True,
        )
        prompt = (
            "Tool approval required\n"
            f"Tool: {tool_call.name}\n"
            f"Arguments: {rendered_arguments}\n"
            f"Reason: {reason}\n"
            "Approve? [y/N]: "
        )
        print(
            prompt,
            end="",
            file=sys.stderr,
            flush=True,
        )
        answer = await asyncio.to_thread(
            self._input_reader,
        )

        if not isinstance(answer, str):
            raise TypeError("input reader must return a string")

        return answer.strip().casefold() in {
            "y",
            "yes",
        }
