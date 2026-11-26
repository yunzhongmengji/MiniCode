"""Budget-driven dual-view context manager backed by the Event Ledger."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from minicode.context.tokenizer import ApproximateTokenEstimator, TokenEstimator
from minicode.schemas.events import EventType
from minicode.schemas.messages import HistoryEntry, ToolResultRecord
from minicode.storage.event_ledger import EventLedger
from minicode.tools.spec import ToolSpec


class ContextBudgetConfig(BaseModel):
    """Budget and retention rules for building the model-visible context view."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_context_tokens: int = Field(gt=0)
    protected_recent_tool_results: int = Field(default=1, ge=0)
    min_compress_tokens: int = Field(default=24, ge=1)
    summary_max_chars: int = Field(default=80, ge=16)


class CompressedArtifactRef(BaseModel):
    """Metadata describing one tool result replaced by a retrievable reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int = Field(ge=1)
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    original_tokens: int = Field(ge=0)
    placeholder_tokens: int = Field(ge=0)
    saved_tokens: int = Field(ge=1)
    summary: str


class ModelContextView(BaseModel):
    """Projected model-visible context distinct from the ledger's full history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation: tuple[HistoryEntry, ...]
    original_tokens: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    max_context_tokens: int = Field(gt=0)
    compressed_refs: tuple[CompressedArtifactRef, ...] = ()


def _make_compact_summary(output: str, *, max_chars: int) -> str:
    """Create a single-line compact preview safe for reference placeholders."""
    collapsed = " ".join(output.split()).replace('"', "'")
    if len(collapsed) <= max_chars:
        return collapsed
    return f"{collapsed[: max_chars - 3]}..."


def format_artifact_reference(
    *,
    event_id: int,
    tool_name: str,
    summary: str,
) -> str:
    """Format a compact, retrievable placeholder for a compressed tool output."""
    return f'[Ref: event_id={event_id}, tool={tool_name}, summary="{summary}"]'


class BudgetedContextManager:
    """Dynamically project full history into a token-budgeted model-visible view."""

    def __init__(
        self,
        *,
        event_ledger: EventLedger,
        config: ContextBudgetConfig,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self._event_ledger = event_ledger
        self._config = config
        self._estimator: TokenEstimator = (
            ApproximateTokenEstimator() if estimator is None else estimator
        )

    @property
    def config(self) -> ContextBudgetConfig:
        """Return the active context budget configuration."""
        return self._config

    @property
    def estimator(self) -> TokenEstimator:
        """Return the active token estimator."""
        return self._estimator

    def build_view(
        self,
        *,
        session_id: str,
        full_history: Sequence[HistoryEntry],
        instructions: Sequence[str] = (),
        tool_specs: Sequence[ToolSpec] = (),
    ) -> ModelContextView:
        """Build a model-visible view without mutating the canonical full history."""
        history_list = list(full_history)
        overhead = self._estimator.estimate_overhead(
            instructions=instructions,
            tool_specs=tool_specs,
        )
        entry_tokens = [
            self._estimator.estimate_entry(entry) for entry in history_list
        ]
        original_tokens = overhead + sum(entry_tokens)
        budget = self._config.max_context_tokens

        if original_tokens <= budget:
            return ModelContextView(
                conversation=tuple(history_list),
                original_tokens=original_tokens,
                estimated_tokens=original_tokens,
                max_context_tokens=budget,
            )

        call_id_to_event_id = self._index_tool_events(session_id)
        tool_result_indices = [
            idx
            for idx, entry in enumerate(history_list)
            if isinstance(entry, ToolResultRecord)
        ]

        protected_count = self._config.protected_recent_tool_results
        protected_indices = (
            set(tool_result_indices[-protected_count:])
            if protected_count > 0
            else set()
        )

        # Build compression candidates from older tool results not in the protected tail.
        candidates: list[
            tuple[int, int, ToolResultRecord, CompressedArtifactRef]
        ] = []
        for idx in tool_result_indices:
            if idx in protected_indices:
                continue
            entry = history_list[idx]
            assert isinstance(entry, ToolResultRecord)
            event_id = call_id_to_event_id.get(entry.call_id)
            if event_id is None:
                continue

            orig_tok = entry_tokens[idx]
            if orig_tok < self._config.min_compress_tokens:
                continue

            summary = _make_compact_summary(
                entry.output,
                max_chars=self._config.summary_max_chars,
            )
            placeholder_text = format_artifact_reference(
                event_id=event_id,
                tool_name=entry.name,
                summary=summary,
            )
            replaced_entry = entry.model_copy(update={"output": placeholder_text})
            placeholder_tok = self._estimator.estimate_entry(replaced_entry)
            saved_tok = orig_tok - placeholder_tok
            if saved_tok <= 0:
                continue

            ref = CompressedArtifactRef(
                event_id=event_id,
                call_id=entry.call_id,
                tool_name=entry.name,
                original_tokens=orig_tok,
                placeholder_tokens=placeholder_tok,
                saved_tokens=saved_tok,
                summary=summary,
            )
            candidates.append((saved_tok, idx, replaced_entry, ref))

        # Prioritize older, larger outputs: highest token savings first, oldest on ties.
        candidates.sort(key=lambda item: (-item[0], item[1]))

        current_tokens = original_tokens
        applied_refs: list[tuple[int, CompressedArtifactRef]] = []
        for saved_tok, idx, replaced_entry, ref in candidates:
            if current_tokens <= budget:
                break
            history_list[idx] = replaced_entry
            current_tokens -= saved_tok
            applied_refs.append((idx, ref))

        # Keep compressed_refs ordered chronologically by history index.
        applied_refs.sort(key=lambda item: item[0])

        return ModelContextView(
            conversation=tuple(history_list),
            original_tokens=original_tokens,
            estimated_tokens=current_tokens,
            max_context_tokens=budget,
            compressed_refs=tuple(ref for _, ref in applied_refs),
        )

    def _index_tool_events(self, session_id: str) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for event in self._event_ledger.list_events(session_id):
            if event.event_type is not EventType.TOOL_EXECUTED:
                continue
            if event.event_id is None:
                continue
            call_id = event.payload.get("call_id")
            if isinstance(call_id, str) and call_id:
                mapping[call_id] = event.event_id
        return mapping
