"""Start one Coding Agent evaluation from its case contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from minicode import cli
from minicode.context_experiment_protocol import (
    BudgetedContextExperimentProtocol,
    load_budgeted_context_experiment_protocol,
)
from minicode.core.context_projection_config import (
    BudgetedContextProjectionConfiguration,
)
from minicode.evaluation_case import load_case_manifest


class EvaluationArm(StrEnum):
    """Context configuration selected for one evaluation run."""

    BASELINE = "baseline"
    PROJECTION = "projection"


@dataclass(frozen=True, slots=True)
class RegisteredContextRunConfiguration:
    """Agent settings resolved from one pre-registered protocol arm."""

    protocol_id: str
    expected_model: str
    budgeted_context_configuration: (
        BudgetedContextProjectionConfiguration | None
    )


def context_threshold_for_arm(arm: EvaluationArm) -> int | None:
    """Translate an experiment arm into the Agent's projection threshold."""
    if arm is EvaluationArm.BASELINE:
        return None

    return 500


def registered_context_run_configuration(
    protocol: BudgetedContextExperimentProtocol,
    *,
    case_id: str,
    arm: EvaluationArm,
) -> RegisteredContextRunConfiguration:
    """Resolve one v4 arm without duplicating its configuration."""
    if case_id not in protocol.cases:
        raise ValueError(
            f"case {case_id} is not registered by protocol {protocol.protocol_id}"
        )

    if protocol.model.provider != "dashscope_openai_compatible":
        raise ValueError(
            "evaluation runner only supports dashscope_openai_compatible protocols"
        )

    if protocol.model.enable_thinking:
        raise ValueError("evaluation runner does not support thinking mode")

    if (
        protocol.model.temperature_control
        != "provider_default_not_set_by_minicode"
    ):
        raise ValueError(
            "evaluation runner only supports provider-default temperature"
        )

    projection_configuration = (
        None
        if arm is EvaluationArm.BASELINE
        else protocol.projection_configuration
    )
    return RegisteredContextRunConfiguration(
        protocol_id=protocol.protocol_id,
        expected_model=protocol.model.name,
        budgeted_context_configuration=projection_configuration,
    )


def build_coding_run_arguments(
    case_root: Path,
) -> tuple[str, ...]:
    """Build CLI arguments from one validated evaluation case."""
    resolved_case_root = case_root.resolve(strict=True)
    manifest = load_case_manifest(resolved_case_root)
    task = (resolved_case_root / "task.txt").read_text(
        encoding="utf-8",
    )

    if not task.strip():
        raise ValueError("evaluation task must not be blank")

    return (
        "run",
        task.strip(),
        "--max-turns",
        str(manifest.budget.max_turns),
        "--max-tool-calls",
        str(manifest.budget.max_tool_calls),
        "--trace",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the evaluation-run argument parser."""
    parser = argparse.ArgumentParser(
        description="Run a prepared MiniCode evaluation workspace.",
    )
    parser.add_argument(
        "--case-root",
        type=Path,
        required=True,
        help="Evaluation case containing case.json and task.txt.",
    )
    parser.add_argument(
        "--arm",
        type=EvaluationArm,
        choices=tuple(EvaluationArm),
        help=(
            "Context experiment arm. Defaults to baseline without a protocol; "
            "required with --context-protocol."
        ),
    )
    parser.add_argument(
        "--context-protocol",
        type=Path,
        help="Pre-registered schema-3 context experiment protocol.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the case task in the current working directory."""
    parser = build_parser()
    args = parser.parse_args(argv)
    arm = EvaluationArm.BASELINE if args.arm is None else args.arm
    registered_configuration: RegisteredContextRunConfiguration | None = None

    if args.context_protocol is not None:
        if args.arm is None:
            parser.error("--arm is required with --context-protocol")

        protocol = load_budgeted_context_experiment_protocol(
            args.context_protocol
        )
        manifest = load_case_manifest(args.case_root.resolve(strict=True))
        registered_configuration = registered_context_run_configuration(
            protocol,
            case_id=manifest.case_id,
            arm=arm,
        )

    return cli.main(
        build_coding_run_arguments(args.case_root),
        max_inline_tool_result_bytes=(
            context_threshold_for_arm(arm)
            if registered_configuration is None
            else None
        ),
        budgeted_context_configuration=(
            None
            if registered_configuration is None
            else registered_configuration.budgeted_context_configuration
        ),
        expected_model=(
            None
            if registered_configuration is None
            else registered_configuration.expected_model
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
