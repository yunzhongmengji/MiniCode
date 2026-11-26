"""Pydantic v2 schemas for multi-file benchmarks and ablation evaluation reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from minicode.schemas.events import utc_now


class BenchmarkCaseSpec(BaseModel):
    """Metadata describing one multi-file benchmark scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected_skill: str = Field(min_length=1)
    verify_script: str = Field(default="verify_test.py", min_length=1)


class AblationConfig(BaseModel):
    """Feature toggle combination for one ablation experiment arm."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    enable_context_compression: bool = True
    max_context_tokens: int = Field(default=1200, gt=0)
    enable_skill_routing: bool = True
    max_turns: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=16, ge=1)


class CaseEvalResult(BaseModel):
    """Measured outcome of running one benchmark case under one ablation config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    ablation_name: str = Field(min_length=1)
    passed: bool
    steps: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    estimated_prompt_tokens: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0)
    loaded_skills: tuple[str, ...] = ()
    compressed_ref_count: int = Field(default=0, ge=0)
    failure_reason: str | None = None
    trace_path: str | None = None


class AblationSummary(BaseModel):
    """Aggregated metrics for one ablation arm across all benchmark cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ablation_name: str = Field(min_length=1)
    enable_context_compression: bool
    enable_skill_routing: bool
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    avg_steps: float = Field(ge=0.0)
    total_tokens: int = Field(ge=0)
    avg_prompt_tokens: float = Field(ge=0.0)
    avg_duration_seconds: float = Field(ge=0.0)
    results: tuple[CaseEvalResult, ...] = ()


class EvaluationReport(BaseModel):
    """Complete ablation comparison report exportable as JSON or Markdown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime = Field(default_factory=utc_now)
    summaries: tuple[AblationSummary, ...]

    def render_markdown(self) -> str:
        """Render a Markdown comparison table across all ablation arms."""
        lines = [
            "# MiniCode Ablation Evaluation Report",
            "",
            f"Generated at: `{self.generated_at.isoformat()}`",
            "",
            "## Summary Comparison",
            "",
            (
                "| Ablation | Context Compression | Skill Routing | Pass Rate | "
                "Avg Steps | Total Tokens | Avg Prompt Tokens | Avg Duration (s) |"
            ),
            "|---|---|---|---|---|---|---|---|",
        ]
        for s in self.summaries:
            lines.append(
                f"| `{s.ablation_name}` | "
                f"{'ON' if s.enable_context_compression else 'OFF'} | "
                f"{'ON' if s.enable_skill_routing else 'OFF'} | "
                f"{s.passed_cases}/{s.total_cases} ({s.pass_rate * 100:.1f}%) | "
                f"{s.avg_steps:.2f} | "
                f"{s.total_tokens} | "
                f"{s.avg_prompt_tokens:.1f} | "
                f"{s.avg_duration_seconds:.3f} |"
            )

        lines.extend(["", "## Per-Case Details", ""])
        for s in self.summaries:
            lines.append(f"### `{s.ablation_name}`")
            lines.append("")
            lines.append(
                "| Case | Passed | Steps | Prompt Tokens | Loaded Skills | Trace |"
            )
            lines.append("|---|---|---|---|---|---|")
            for r in s.results:
                skills_str = ", ".join(r.loaded_skills) if r.loaded_skills else "-"
                trace_str = f"`{r.trace_path}`" if r.trace_path else "-"
                lines.append(
                    f"| `{r.case_id}` | "
                    f"{'PASS' if r.passed else 'FAIL'} | "
                    f"{r.steps} | "
                    f"{r.estimated_prompt_tokens} | "
                    f"{skills_str} | "
                    f"{trace_str} |"
                )
            lines.append("")
        return "\n".join(lines)
