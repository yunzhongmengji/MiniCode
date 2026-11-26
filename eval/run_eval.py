"""CLI entry point for running MiniCode's ablation evaluation suite."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from minicode.eval import (
    AblationConfig,
    BenchmarkCaseSpec,
    ModelBuilder,
    build_scripted_benchmark_model,
    default_ablation_configs,
    run_ablation_suite,
)
from minicode.models import (
    DashScopeConfig,
    Model,
    build_dashscope_client,
    build_dashscope_model,
)


def _build_model_factory(mode: str) -> ModelBuilder:
    if mode == "scripted":
        return build_scripted_benchmark_model

    def _dashscope(spec: BenchmarkCaseSpec, ablation: AblationConfig) -> Model:
        _ = (spec, ablation)
        config = DashScopeConfig.from_environment(os.environ)
        client = build_dashscope_client(config)
        return build_dashscope_model(config, client=client)

    return _dashscope


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run MiniCode's ablation evaluation suite."
    )
    parser.add_argument(
        "--mode",
        choices=("scripted", "dashscope"),
        default="scripted",
        help="Evaluation model backend (default: scripted offline mode).",
    )
    parser.add_argument(
        "--benchmarks-dir",
        type=Path,
        default=Path("eval/benchmarks"),
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path("skills"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/reports/latest"),
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_ablation_suite(
            benchmarks_dir=args.benchmarks_dir,
            skills_dir=args.skills_dir,
            output_dir=args.output_dir,
            model_builder=_build_model_factory(args.mode),
            ablations=default_ablation_configs(),
        )
    )
    print(report.render_markdown())


if __name__ == "__main__":
    main()
