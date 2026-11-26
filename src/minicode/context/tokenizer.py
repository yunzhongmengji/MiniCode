"""Deterministic token estimation for budget-driven context management."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Protocol

from minicode.schemas.messages import (
    HistoryEntry,
    MessageRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from minicode.tools.spec import ToolSpec


class TokenEstimator(Protocol):
    """Estimate token counts for model inputs."""

    def estimate_text(self, text: str) -> int:
        """Estimate tokens for one text string."""
        ...

    def estimate_entry(self, entry: HistoryEntry) -> int:
        """Estimate tokens for one conversation history entry."""
        ...

    def estimate_overhead(
        self,
        *,
        instructions: Sequence[str],
        tool_specs: Sequence[ToolSpec],
    ) -> int:
        """Estimate fixed request overhead for instructions and tool specs."""
        ...


class ApproximateTokenEstimator:
    """Fast, deterministic UTF-8 byte-based token estimator (~4 bytes/token)."""

    def __init__(
        self,
        *,
        bytes_per_token: int = 4,
        per_message_overhead: int = 4,
    ) -> None:
        if bytes_per_token <= 0:
            raise ValueError("bytes_per_token must be greater than zero")
        if per_message_overhead < 0:
            raise ValueError("per_message_overhead must not be negative")
        self._bytes_per_token = bytes_per_token
        self._per_message_overhead = per_message_overhead

    def estimate_text(self, text: str) -> int:
        """Estimate token count from UTF-8 byte length."""
        if not text:
            return 0
        byte_len = len(text.encode("utf-8"))
        return max(1, math.ceil(byte_len / self._bytes_per_token))

    def estimate_entry(self, entry: HistoryEntry) -> int:
        """Estimate token count for a single history entry."""
        if isinstance(entry, MessageRecord):
            return self._per_message_overhead + self.estimate_text(entry.content)
        if isinstance(entry, ToolCallRecord):
            args_json = json.dumps(entry.arguments, ensure_ascii=False, sort_keys=True)
            return (
                self._per_message_overhead
                + self.estimate_text(entry.name)
                + self.estimate_text(args_json)
            )
        assert isinstance(entry, ToolResultRecord)
        return (
            self._per_message_overhead
            + self.estimate_text(entry.name)
            + self.estimate_text(entry.output)
        )

    def estimate_overhead(
        self,
        *,
        instructions: Sequence[str],
        tool_specs: Sequence[ToolSpec],
    ) -> int:
        """Estimate token overhead for system instructions and tool definitions."""
        total = 0
        for instruction in instructions:
            total += self._per_message_overhead + self.estimate_text(instruction)
        for spec in tool_specs:
            schema_json = json.dumps(
                spec.arguments_type.model_json_schema(),
                ensure_ascii=False,
                sort_keys=True,
            )
            total += (
                self._per_message_overhead
                + self.estimate_text(spec.name)
                + self.estimate_text(spec.description)
                + self.estimate_text(schema_json)
            )
        return total
