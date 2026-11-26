"""Automated ablation evaluation runner with independent pytest verification."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from minicode.context import ApproximateTokenEstimator
from minicode.eval.schemas import (
    AblationConfig,
    AblationSummary,
    BenchmarkCaseSpec,
    CaseEvalResult,
    EvaluationReport,
)
from minicode.models.base import Model
from minicode.runtime import (
    DEFAULT_CODING_SYSTEM_PROMPT,
    ToolRiskPolicy,
    Workspace,
    build_local_tool_registry,
    build_runtime,
    replay,
)
from minicode.schemas import EventType
from minicode.skills.lazy import LazySkillRegistry
from minicode.storage import SqliteRuntimeStorage

ModelBuilder = Callable[[BenchmarkCaseSpec, AblationConfig], Model]


def discover_benchmarks(
    benchmarks_dir: Path,
) -> tuple[tuple[BenchmarkCaseSpec, Path], ...]:
    """Discover all benchmark cases containing a case.json descriptor."""
    if not benchmarks_dir.is_dir():
        raise FileNotFoundError(f"benchmarks directory not found: {benchmarks_dir}")
    cases: list[tuple[BenchmarkCaseSpec, Path]] = []
    for case_dir in sorted(benchmarks_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        spec_path = case_dir / "case.json"
        if not spec_path.is_file():
            continue
        spec = BenchmarkCaseSpec.model_validate_json(
            spec_path.read_text(encoding="utf-8")
        )
        cases.append((spec, case_dir))
    return tuple(cases)


def default_ablation_configs() -> tuple[AblationConfig, ...]:
    """Return standard ablation arms comparing context compression and skill routing."""
    return (
        AblationConfig(
            name="full_system",
            enable_context_compression=True,
            max_context_tokens=1200,
            enable_skill_routing=True,
        ),
        AblationConfig(
            name="no_skill_routing",
            enable_context_compression=True,
            max_context_tokens=1200,
            enable_skill_routing=False,
        ),
        AblationConfig(
            name="no_context_compression",
            enable_context_compression=False,
            max_context_tokens=1200,
            enable_skill_routing=True,
        ),
    )


def _run_independent_pytest(
    *,
    workspace_copy: Path,
    verify_script: Path,
) -> tuple[bool, str]:
    """Run the independent pytest acceptance script against the modified workspace."""
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{workspace_copy}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(workspace_copy)
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(verify_script)],
        cwd=str(workspace_copy),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = f"{proc.stdout}\n{proc.stderr}".strip()
    return proc.returncode == 0, output


async def run_single_case(
    *,
    spec: BenchmarkCaseSpec,
    case_dir: Path,
    skills_dir: Path,
    ablation: AblationConfig,
    model: Model,
    traces_dir: Path,
) -> CaseEvalResult:
    """Execute one benchmark case in an isolated temp workspace and verify with pytest."""
    started = time.perf_counter()
    estimator = ApproximateTokenEstimator()

    with tempfile.TemporaryDirectory(prefix=f"minicode_eval_{spec.case_id}_") as tmp:
        tmp_path = Path(tmp)
        workspace_copy = tmp_path / "workspace"
        shutil.copytree(case_dir / "workspace", workspace_copy)
        db_path = tmp_path / "eval.sqlite3"

        skill_registry = LazySkillRegistry.discover(skills_dir)
        extra_instructions: list[str] = []
        if ablation.enable_skill_routing:
            extra_instructions.append(skill_registry.render_metadata_prompt())
            tool_skill_registry: LazySkillRegistry | None = skill_registry
        else:
            extra_instructions.append(skill_registry.render_all_full_instructions())
            tool_skill_registry = None

        storage = SqliteRuntimeStorage(db_path)
        try:
            workspace = Workspace(workspace_copy)
            tool_registry = build_local_tool_registry(
                workspace=workspace,
                skill_registry=tool_skill_registry,
            )
            eval_policy = ToolRiskPolicy(approval_required_levels=())
            runtime = build_runtime(
                model=model,
                storage=storage,
                tool_registry=tool_registry,
                risk_policy=eval_policy,
                max_context_tokens=(
                    ablation.max_context_tokens
                    if ablation.enable_context_compression
                    else None
                ),
                estimator=estimator,
                extra_instructions=tuple(extra_instructions),
                max_turns=ablation.max_turns,
                max_tool_calls=ablation.max_tool_calls,
            )

            session_id = f"eval_{ablation.name}_{spec.case_id}"
            run_result = await runtime.start(spec.prompt, session_id=session_id)

            # Independent acceptance verification.
            verify_script = (case_dir / spec.verify_script).resolve()
            passed, verify_output = _run_independent_pytest(
                workspace_copy=workspace_copy,
                verify_script=verify_script,
            )

            # Archive trajectory replay for every run (especially failed runs).
            arm_trace_dir = traces_dir / ablation.name
            arm_trace_dir.mkdir(parents=True, exist_ok=True)
            trace_file = arm_trace_dir / f"{spec.case_id}.txt"
            session_replay = replay(session_id, storage)
            trace_text = (
                f"{session_replay.render_text()}\n\n"
                f"=== INDEPENDENT PYTEST VERIFICATION (passed={passed}) ===\n"
                f"{verify_output}\n"
            )
            trace_file.write_text(trace_text, encoding="utf-8")

            # Count compressed references & estimated prompt tokens.
            events = storage.event_ledger.list_events(session_id)
            compressed_refs = sum(
                len(ev.payload.get("compressed_event_ids", []))
                for ev in events
                if ev.event_type is EventType.REASONING_COMPLETED
                and isinstance(ev.payload.get("compressed_event_ids"), list)
            )
            all_instructions = (DEFAULT_CODING_SYSTEM_PROMPT, *extra_instructions)
            estimated_prompt_tokens = estimator.estimate_overhead(
                instructions=all_instructions,
                tool_specs=tool_registry.specs,
            ) + estimator.estimate_text(spec.prompt)

            duration = time.perf_counter() - started
            return CaseEvalResult(
                case_id=spec.case_id,
                ablation_name=ablation.name,
                passed=passed,
                steps=run_result.step,
                total_input_tokens=run_result.total_input_tokens,
                total_output_tokens=run_result.total_output_tokens,
                estimated_prompt_tokens=estimated_prompt_tokens,
                duration_seconds=round(duration, 4),
                loaded_skills=skill_registry.loaded_skill_names,
                compressed_ref_count=compressed_refs,
                failure_reason=None if passed else verify_output[:400],
                trace_path=str(trace_file),
            )
        finally:
            storage.close()


async def run_ablation_suite(
    *,
    benchmarks_dir: Path,
    skills_dir: Path,
    output_dir: Path,
    model_builder: ModelBuilder,
    ablations: Sequence[AblationConfig] | None = None,
) -> EvaluationReport:
    """Run all benchmark cases across all ablation arms and write JSON/MD reports."""
    cases = discover_benchmarks(benchmarks_dir)
    active_ablations = (
        default_ablation_configs() if ablations is None else tuple(ablations)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = output_dir / "traces"

    summaries: list[AblationSummary] = []
    for ablation in active_ablations:
        arm_results: list[CaseEvalResult] = []
        for spec, case_dir in cases:
            model = model_builder(spec, ablation)
            res = await run_single_case(
                spec=spec,
                case_dir=case_dir,
                skills_dir=skills_dir,
                ablation=ablation,
                model=model,
                traces_dir=traces_dir,
            )
            arm_results.append(res)

        total = len(arm_results)
        passed = sum(1 for r in arm_results if r.passed)
        total_tokens = sum(
            r.total_input_tokens + r.total_output_tokens for r in arm_results
        )
        summaries.append(
            AblationSummary(
                ablation_name=ablation.name,
                enable_context_compression=ablation.enable_context_compression,
                enable_skill_routing=ablation.enable_skill_routing,
                total_cases=total,
                passed_cases=passed,
                pass_rate=(passed / total) if total > 0 else 0.0,
                avg_steps=(
                    sum(r.steps for r in arm_results) / total if total > 0 else 0.0
                ),
                total_tokens=total_tokens,
                avg_prompt_tokens=(
                    sum(r.estimated_prompt_tokens for r in arm_results) / total
                    if total > 0
                    else 0.0
                ),
                avg_duration_seconds=(
                    sum(r.duration_seconds for r in arm_results) / total
                    if total > 0
                    else 0.0
                ),
                results=tuple(arm_results),
            )
        )

    report = EvaluationReport(summaries=tuple(summaries))
    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        report.render_markdown() + "\n",
        encoding="utf-8",
    )
    return report
