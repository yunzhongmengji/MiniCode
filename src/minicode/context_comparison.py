"""Run deterministic baseline-versus-projection context comparisons."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory

from minicode.coding_agent import build_coding_agent
from minicode.context_trace import summarize_context_trace
from minicode.core.checkpoints import InMemoryCheckpointStore, RunCheckpoint
from minicode.core.events import EventKind, InMemoryEventLedger, LedgerEvent
from minicode.core.model import ModelRequest, ModelResponse
from minicode.core.query_loop import RunResult, StopReason
from minicode.core.replay import RunReplay
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.tools.process import AsyncioProcessRunner
from minicode.workspace import Workspace

_FINAL_ANSWER = "Historical evidence verified."


class ContextComparisonScenario(StrEnum):
    """Fixed task policies used by the offline context comparison."""

    EAGER_HISTORICAL_READBACK = "eager_historical_readback"
    NO_HISTORICAL_READBACK = "no_historical_readback"


@dataclass(frozen=True, slots=True)
class ContextRunMetrics:
    """Aggregate context and readback facts from one event stream."""

    run_outcome: str
    model_call_count: int
    tool_execution_count: int
    model_visible_bytes: int
    canonical_bytes: int
    projection_bytes_saved: int
    tool_result_bytes_saved: int
    changed_tool_result_count: int
    successful_readback_count: int
    failed_readback_count: int
    cancelled_readback_count: int

    def to_payload(self) -> dict[str, str | int]:
        """Return a JSON-compatible metrics document."""
        return {
            "run_outcome": self.run_outcome,
            "model_call_count": self.model_call_count,
            "tool_execution_count": self.tool_execution_count,
            "model_visible_bytes": self.model_visible_bytes,
            "canonical_bytes": self.canonical_bytes,
            "projection_bytes_saved": self.projection_bytes_saved,
            "tool_result_bytes_saved": self.tool_result_bytes_saved,
            "changed_tool_result_count": self.changed_tool_result_count,
            "successful_readback_count": self.successful_readback_count,
            "failed_readback_count": self.failed_readback_count,
            "cancelled_readback_count": self.cancelled_readback_count,
        }


@dataclass(frozen=True, slots=True)
class ContextCostBreakdown:
    """Explain how projection savings and run-shape costs form net savings."""

    gross_projection_savings_bytes: int
    conditional_tool_overhead_bytes: int
    additional_run_shape_overhead_bytes: int
    run_shape_overhead_bytes: int
    net_model_visible_savings_bytes: int

    @property
    def equation_holds(self) -> bool:
        """Return whether gross savings minus overhead equals net savings."""
        return (
            self.gross_projection_savings_bytes - self.run_shape_overhead_bytes
            == self.net_model_visible_savings_bytes
        )

    def to_payload(self) -> dict[str, int | bool]:
        """Return the cost equation as a JSON-compatible document."""
        return {
            "gross_projection_savings_bytes": self.gross_projection_savings_bytes,
            "conditional_tool_overhead_bytes": self.conditional_tool_overhead_bytes,
            "additional_run_shape_overhead_bytes": (
                self.additional_run_shape_overhead_bytes
            ),
            "run_shape_overhead_bytes": self.run_shape_overhead_bytes,
            "net_model_visible_savings_bytes": self.net_model_visible_savings_bytes,
            "equation_holds": self.equation_holds,
        }


@dataclass(frozen=True, slots=True)
class ContextComparisonReport:
    """Compare deterministic baseline and projected Agent runs."""

    scenario: ContextComparisonScenario
    baseline: ContextRunMetrics
    projected: ContextRunMetrics
    final_answer_matches: bool
    both_runs_completed: bool
    checkpoints_match_run_histories: bool

    @property
    def model_visible_byte_difference(self) -> int:
        """Return baseline bytes minus projected bytes across all calls."""
        return self.baseline.model_visible_bytes - self.projected.model_visible_bytes

    @property
    def cost_breakdown(self) -> ContextCostBreakdown:
        """Return the gross-savings-minus-overhead cost equation."""
        conditional_tool_overhead = (
            self.projected.tool_result_bytes_saved
            - self.projected.projection_bytes_saved
        )
        additional_run_shape_overhead = (
            self.projected.canonical_bytes - self.baseline.model_visible_bytes
        )
        return ContextCostBreakdown(
            gross_projection_savings_bytes=(self.projected.tool_result_bytes_saved),
            conditional_tool_overhead_bytes=conditional_tool_overhead,
            additional_run_shape_overhead_bytes=additional_run_shape_overhead,
            run_shape_overhead_bytes=(
                conditional_tool_overhead + additional_run_shape_overhead
            ),
            net_model_visible_savings_bytes=self.model_visible_byte_difference,
        )

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-compatible comparison report."""
        return {
            "schema_version": 2,
            "measurement_unit": "canonical_json_utf8_bytes_not_model_tokens",
            "scenario": self.scenario,
            "baseline": self.baseline.to_payload(),
            "projected": self.projected.to_payload(),
            "cost_breakdown": self.cost_breakdown.to_payload(),
            "comparison": {
                "model_visible_byte_difference": (self.model_visible_byte_difference),
                "projected_used_fewer_model_visible_bytes": (
                    self.model_visible_byte_difference > 0
                ),
                "final_answer_matches": self.final_answer_matches,
                "both_runs_completed": self.both_runs_completed,
                "checkpoints_match_run_histories": (
                    self.checkpoints_match_run_histories
                ),
            },
        }


@dataclass(frozen=True, slots=True)
class ContextComparisonSuite:
    """Combine the two endpoint scenarios into one illustrative cost model."""

    no_readback: ContextComparisonReport
    eager_readback: ContextComparisonReport

    @property
    def break_even_eager_task_share_numerator(self) -> int:
        """Return the profitable endpoint's net byte saving."""
        return self.no_readback.model_visible_byte_difference

    @property
    def break_even_eager_task_share_denominator(self) -> int:
        """Return the byte swing between the two endpoint outcomes."""
        return (
            self.no_readback.model_visible_byte_difference
            - self.eager_readback.model_visible_byte_difference
        )

    @property
    def break_even_eager_task_share_basis_points(self) -> int:
        """Return the endpoint-mixture break-even share in basis points."""
        numerator = self.break_even_eager_task_share_numerator
        denominator = self.break_even_eager_task_share_denominator

        if numerator <= 0 or denominator <= numerator:
            raise ValueError("endpoint results do not straddle break-even")

        return round(numerator * 10_000 / denominator)

    def to_payload(self) -> dict[str, object]:
        """Return both endpoints and their illustrative break-even estimate."""
        return {
            "schema_version": 2,
            "measurement_unit": "canonical_json_utf8_bytes_not_model_tokens",
            "scenarios": {
                "no_historical_readback": self.no_readback.to_payload(),
                "eager_historical_readback": self.eager_readback.to_payload(),
            },
            "illustrative_break_even": {
                "eager_readback_task_share_numerator": (
                    self.break_even_eager_task_share_numerator
                ),
                "eager_readback_task_share_denominator": (
                    self.break_even_eager_task_share_denominator
                ),
                "eager_readback_task_share_basis_points": (
                    self.break_even_eager_task_share_basis_points
                ),
                "assumption": "linear_mix_of_these_two_deterministic_endpoints",
                "is_production_threshold": False,
            },
        }


@dataclass(frozen=True, slots=True)
class _RecordedRun:
    result: RunResult
    checkpoint: RunCheckpoint
    replay: RunReplay


class _ConditionalContextModel:
    """Follow one fixed policy that reacts to full output versus a reference."""

    def __init__(self, scenario: ContextComparisonScenario) -> None:
        self._scenario = scenario
        self._requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Read two files, recover a reference if needed, then finish."""
        self._requests.append(request)
        call_number = len(self._requests)

        if call_number == 1:
            return ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        call_id="call_read_old",
                        name="read_file",
                        arguments={"path": "old.txt"},
                    ),
                ),
            )

        if call_number == 2:
            return ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        call_id="call_read_latest",
                        name="read_file",
                        arguments={"path": "latest.txt"},
                    ),
                ),
            )

        if call_number == 3:
            if self._scenario is ContextComparisonScenario.NO_HISTORICAL_READBACK:
                return ModelResponse(content=_FINAL_ANSWER)

            old_result = _result_for_call(request, "call_read_old")

            if _is_historical_reference(old_result.output):
                return ModelResponse(
                    content="",
                    tool_calls=(
                        ToolCall(
                            call_id="call_restore_old",
                            name="read_tool_result",
                            arguments={"call_id": "call_read_old"},
                        ),
                    ),
                )

            return ModelResponse(content=_FINAL_ANSWER)

        if call_number == 4:
            restored_result = _result_for_call(request, "call_restore_old")

            if not restored_result.output.startswith('File "old.txt":'):
                raise RuntimeError("historical readback did not return the old file")

            return ModelResponse(content=_FINAL_ANSWER)

        raise RuntimeError("deterministic context model exceeded its scenario")


def _result_for_call(request: ModelRequest, call_id: str) -> ToolResult:
    for item in request.conversation:
        if isinstance(item, ToolResult) and item.call_id == call_id:
            return item

    raise RuntimeError(f"model request is missing tool result: {call_id}")


def _is_historical_reference(output: str) -> bool:
    try:
        decoded: object = json.loads(output)
    except json.JSONDecodeError:
        return False

    return (
        isinstance(decoded, Mapping)
        and decoded.get("kind") == "historical_tool_result_reference"
        and decoded.get("retrieval_tool") == "read_tool_result"
    )


async def run_offline_context_comparison(
    scenario: ContextComparisonScenario = (
        ContextComparisonScenario.EAGER_HISTORICAL_READBACK
    ),
) -> ContextComparisonReport:
    """Run the fixed scenario once without and once with projection."""
    baseline = await _run_variant(projected=False, scenario=scenario)
    projected = await _run_variant(projected=True, scenario=scenario)
    baseline_metrics = summarize_context_events(baseline.replay.events)
    projected_metrics = summarize_context_events(projected.replay.events)

    return ContextComparisonReport(
        scenario=scenario,
        baseline=baseline_metrics,
        projected=projected_metrics,
        final_answer_matches=(
            baseline.result.response.content == projected.result.response.content
        ),
        both_runs_completed=(
            baseline.result.stop_reason is StopReason.COMPLETED
            and projected.result.stop_reason is StopReason.COMPLETED
            and baseline.checkpoint.is_completed
            and projected.checkpoint.is_completed
        ),
        checkpoints_match_run_histories=(
            baseline.checkpoint.message_history == baseline.result.message_history
            and projected.checkpoint.message_history == projected.result.message_history
        ),
    )


async def run_offline_context_comparison_suite() -> ContextComparisonSuite:
    """Run both deterministic endpoint scenarios and combine their costs."""
    no_readback = await run_offline_context_comparison(
        ContextComparisonScenario.NO_HISTORICAL_READBACK
    )
    eager_readback = await run_offline_context_comparison(
        ContextComparisonScenario.EAGER_HISTORICAL_READBACK
    )
    return ContextComparisonSuite(
        no_readback=no_readback,
        eager_readback=eager_readback,
    )


async def _run_variant(
    *,
    projected: bool,
    scenario: ContextComparisonScenario,
) -> _RecordedRun:
    with TemporaryDirectory(prefix="minicode-context-comparison-") as directory:
        workspace_root = Path(directory)
        (workspace_root / "old.txt").write_text(
            "historical evidence line\n" * 200,
            encoding="utf-8",
        )
        (workspace_root / "latest.txt").write_text(
            "latest evidence\n",
            encoding="utf-8",
        )
        run_id = "run_projected" if projected else "run_baseline"
        ledger = InMemoryEventLedger(run_id=run_id)
        checkpoint_store = InMemoryCheckpointStore()
        agent = build_coding_agent(
            model=_ConditionalContextModel(scenario),
            workspace=Workspace(workspace_root),
            process_runner=AsyncioProcessRunner(),
            event_ledger=ledger,
            checkpoint_store=checkpoint_store,
            max_turns=4,
            max_tool_calls=3,
            max_inline_tool_result_bytes=500 if projected else None,
        )
        result = await agent.run("Compare historical and latest evidence.")
        checkpoint = checkpoint_store.latest(run_id)

        if checkpoint is None:
            raise RuntimeError("offline comparison did not save a checkpoint")

        return _RecordedRun(
            result=result,
            checkpoint=checkpoint,
            replay=RunReplay(ledger.events),
        )


def summarize_context_events(
    events: Sequence[LedgerEvent],
) -> ContextRunMetrics:
    """Aggregate validated context metrics and historical readbacks."""
    replay = RunReplay(events)

    if not replay.is_finished or replay.outcome is None:
        raise ValueError("context comparison requires a finished event stream")

    context_metrics = summarize_context_trace(replay.events)
    tool_result_bytes_saved = 0

    for event in replay.events:
        if event.kind is EventKind.MODEL_CALL_STARTED:
            projection = _required_mapping(event.payload, "context_projection")
            tool_result_bytes_saved += _required_integer(
                projection,
                "tool_result_bytes_saved",
            )

    return ContextRunMetrics(
        run_outcome=replay.outcome,
        model_call_count=context_metrics.model_call_count,
        tool_execution_count=replay.tool_execution_count,
        model_visible_bytes=context_metrics.model_visible_bytes,
        canonical_bytes=context_metrics.canonical_bytes,
        projection_bytes_saved=context_metrics.projection_bytes_saved,
        tool_result_bytes_saved=tool_result_bytes_saved,
        changed_tool_result_count=context_metrics.changed_tool_result_count,
        successful_readback_count=context_metrics.successful_readback_count,
        failed_readback_count=context_metrics.failed_readback_count,
        cancelled_readback_count=context_metrics.cancelled_readback_count,
    )


def _required_mapping(
    source: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = source.get(key)

    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")

    return value


def _required_integer(
    source: Mapping[str, object],
    key: str,
) -> int:
    value = source.get(key)

    if type(value) is not int:
        raise TypeError(f"{key} must be an integer")

    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Print the deterministic comparison as JSON."""
    parser = argparse.ArgumentParser(
        description="Compare full and projected Agent context offline.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--scenario",
        choices=tuple(ContextComparisonScenario),
        default=ContextComparisonScenario.EAGER_HISTORICAL_READBACK,
    )
    selection.add_argument(
        "--suite",
        action="store_true",
        help="run both endpoint scenarios and estimate their break-even mix",
    )
    arguments = parser.parse_args(argv)
    if arguments.suite:
        payload = asyncio.run(run_offline_context_comparison_suite()).to_payload()
    else:
        scenario = ContextComparisonScenario(arguments.scenario)
        payload = asyncio.run(run_offline_context_comparison(scenario)).to_payload()
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
