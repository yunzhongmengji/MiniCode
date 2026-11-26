"""Benchmark discovery and ablation evaluation engine for MiniCode."""

from minicode.eval.runner import (
    ModelBuilder,
    default_ablation_configs,
    discover_benchmarks,
    run_ablation_suite,
    run_single_case,
)
from minicode.eval.schemas import (
    AblationConfig,
    AblationSummary,
    BenchmarkCaseSpec,
    CaseEvalResult,
    EvaluationReport,
)
from minicode.eval.scripted import (
    ScriptedBenchmarkModel,
    build_scripted_benchmark_model,
)

__all__ = [
    "AblationConfig",
    "AblationSummary",
    "BenchmarkCaseSpec",
    "CaseEvalResult",
    "EvaluationReport",
    "ModelBuilder",
    "ScriptedBenchmarkModel",
    "build_scripted_benchmark_model",
    "default_ablation_configs",
    "discover_benchmarks",
    "run_ablation_suite",
    "run_single_case",
]
