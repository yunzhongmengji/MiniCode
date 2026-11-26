"""Tests for lazy Skill routing/loading and the ablation evaluation suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from minicode.eval import (
    AblationConfig,
    build_scripted_benchmark_model,
    discover_benchmarks,
    run_ablation_suite,
)
from minicode.eval.runner import _run_independent_pytest
from minicode.skills.lazy import (
    LazySkillRegistry,
    LoadSkillArguments,
    LoadSkillTool,
)
from minicode.tools.base import ToolExecutionError

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
BENCHMARKS_DIR = REPO_ROOT / "eval" / "benchmarks"


@pytest.mark.asyncio
async def test_lazy_skill_metadata_split_routing_and_on_demand_load() -> None:
    registry = LazySkillRegistry.discover(SKILLS_DIR)
    names = {meta.name for meta in registry.metadata_list}
    assert {"debug_pytest", "fix_imports", "refactor_python"}.issubset(names)

    # Default metadata prompt must be substantially shorter than all full bodies.
    meta_prompt = registry.render_metadata_prompt()
    full_prompt = registry.render_all_full_instructions()
    assert len(meta_prompt) < len(full_prompt)
    assert "# Debug Pytest Strategy" not in meta_prompt
    assert registry.loaded_skill_names == ()

    # Keyword routing selects the expected skill first.
    routed_import = registry.route("Resolve circular ImportError between modules")
    assert routed_import[0].name == "fix_imports"

    routed_pytest = registry.route("Fix failing pytest pagination boundary bug")
    assert routed_pytest[0].name == "debug_pytest"

    # On-demand load_skill tool loads body and records usage.
    tool = LoadSkillTool(registry)
    body = await tool.execute(LoadSkillArguments(name="debug_pytest"))
    assert "# Debug Pytest Strategy" in body
    assert registry.loaded_skill_names == ("debug_pytest",)

    with pytest.raises(ToolExecutionError, match="unknown skill"):
        await tool.execute(LoadSkillArguments(name="nonexistent_skill"))


def test_all_benchmark_cases_fail_before_fixing() -> None:
    cases = discover_benchmarks(BENCHMARKS_DIR)
    assert len(cases) == 4
    for spec, case_dir in cases:
        passed, _ = _run_independent_pytest(
            workspace_copy=case_dir / "workspace",
            verify_script=case_dir / spec.verify_script,
        )
        assert passed is False, f"Benchmark {spec.case_id} should fail before fix"


@pytest.mark.asyncio
async def test_ablation_suite_runs_and_generates_comparison_reports(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "eval_report"
    report = await run_ablation_suite(
        benchmarks_dir=BENCHMARKS_DIR,
        skills_dir=SKILLS_DIR,
        output_dir=output_dir,
        model_builder=build_scripted_benchmark_model,
        ablations=(
            AblationConfig(
                name="full_system",
                enable_context_compression=True,
                enable_skill_routing=True,
            ),
            AblationConfig(
                name="no_skill_routing",
                enable_context_compression=True,
                enable_skill_routing=False,
            ),
        ),
    )

    assert len(report.summaries) == 2
    full_arm, no_skill_arm = report.summaries

    assert full_arm.pass_rate == 1.0
    assert no_skill_arm.pass_rate == 1.0
    # Lazy skill routing uses fewer initial prompt tokens than dumping all full skills.
    assert full_arm.avg_prompt_tokens < no_skill_arm.avg_prompt_tokens
    assert all(len(r.loaded_skills) == 1 for r in full_arm.results)
    assert all(len(r.loaded_skills) == 0 for r in no_skill_arm.results)

    assert (output_dir / "report.json").is_file()
    assert (output_dir / "report.md").is_file()
    md_text = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "full_system" in md_text
    assert "no_skill_routing" in md_text
    assert (
        output_dir / "traces" / "full_system" / "01_cross_file_pricing.txt"
    ).is_file()
