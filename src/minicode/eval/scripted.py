"""Deterministic scripted benchmark model for offline CI ablation verification."""

from __future__ import annotations

from minicode.context import ApproximateTokenEstimator
from minicode.eval.schemas import AblationConfig, BenchmarkCaseSpec
from minicode.models.base import Model, ModelRequest, ModelResponse
from minicode.schemas import TokenUsage, ToolCallRecord
from minicode.skills.lazy import LOAD_SKILL_TOOL_NAME

SCRIPTED_BENCHMARK_FIXES: dict[str, tuple[str, str, str]] = {
    "01_cross_file_pricing": (
        "pricing/checkout.py",
        (
            "    # BUG: applies discount_rate a second time after apply_discount already applied it.\n"
            "    return round(discounted * (1.0 - discount_rate), 2)"
        ),
        "    return discounted",
    ),
    "02_circular_import": (
        "app/models.py",
        (
            "from app.serializers import serialize_user  # BUG: circular top-level import\n\n\n"
            "@dataclass(frozen=True)\nclass User:\n    user_id: int\n    name: str\n\n"
            "    def to_dict(self) -> dict[str, object]:\n        return serialize_user(self)"
        ),
        (
            "@dataclass(frozen=True)\nclass User:\n    user_id: int\n    name: str\n\n"
            "    def to_dict(self) -> dict[str, object]:\n"
            "        from app.serializers import serialize_user\n\n"
            "        return serialize_user(self)"
        ),
    ),
    "03_boundary_pagination": (
        "service/pagination.py",
        (
            "    # BUG: missing validation for page <= 0 / page_size <= 0 and off-by-one start index.\n"
            "    start = page * page_size"
        ),
        (
            "    if page <= 0:\n        raise ValueError('page must be >= 1')\n"
            "    if page_size <= 0:\n        raise ValueError('page_size must be >= 1')\n"
            "    start = (page - 1) * page_size"
        ),
    ),
    "04_async_concurrency_race": (
        "worker/counter.py",
        (
            "    def __init__(self) -> None:\n        self.value = 0\n\n"
            "    async def increment(self) -> int:\n"
            '        """Increment the counter by 1 safely across concurrent tasks."""\n'
            "        # BUG: unprotected read-modify-write across an await yield point.\n"
            "        current = self.value\n"
            "        await asyncio.sleep(0)\n"
            "        self.value = current + 1\n"
            "        return self.value"
        ),
        (
            "    def __init__(self) -> None:\n        self.value = 0\n"
            "        self._lock = asyncio.Lock()\n\n"
            "    async def increment(self) -> int:\n"
            '        """Increment the counter by 1 safely across concurrent tasks."""\n'
            "        async with self._lock:\n"
            "            current = self.value\n"
            "            await asyncio.sleep(0)\n"
            "            self.value = current + 1\n"
            "            return self.value"
        ),
    ),
}


class ScriptedBenchmarkModel:
    """Deterministic model that measures real request tokens and executes real tool fixes."""

    def __init__(self, spec: BenchmarkCaseSpec, ablation: AblationConfig) -> None:
        self._spec = spec
        self._ablation = ablation
        self._estimator = ApproximateTokenEstimator()
        self._turn = 0

    def _estimate_input_tokens(self, request: ModelRequest) -> int:
        total = self._estimator.estimate_overhead(
            instructions=request.instructions,
            tool_specs=request.tool_specs,
        )
        for item in request.conversation:
            total += self._estimator.estimate_text(str(item))
        return total

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self._turn += 1
        in_tok = self._estimate_input_tokens(request)
        path, old_text, new_text = SCRIPTED_BENCHMARK_FIXES[self._spec.case_id]

        if self._turn == 1 and self._ablation.enable_skill_routing:
            return ModelResponse(
                content=f"Loading skill '{self._spec.expected_skill}' on demand.",
                tool_calls=(
                    ToolCallRecord(
                        call_id="c_skill",
                        name=LOAD_SKILL_TOOL_NAME,
                        arguments={"name": self._spec.expected_skill},
                    ),
                ),
                usage=TokenUsage(input_tokens=in_tok, output_tokens=18),
            )

        read_turn = 2 if self._ablation.enable_skill_routing else 1
        edit_turn = read_turn + 1

        if self._turn == read_turn:
            return ModelResponse(
                content=f"Reading target file {path}.",
                tool_calls=(
                    ToolCallRecord(
                        call_id="c_read",
                        name="read_file",
                        arguments={"path": path},
                    ),
                ),
                usage=TokenUsage(input_tokens=in_tok, output_tokens=16),
            )

        if self._turn == edit_turn:
            return ModelResponse(
                content=f"Applying minimal fix to {path}.",
                tool_calls=(
                    ToolCallRecord(
                        call_id="c_edit",
                        name="edit_file",
                        arguments={
                            "path": path,
                            "old_text": old_text,
                            "new_text": new_text,
                        },
                    ),
                ),
                usage=TokenUsage(input_tokens=in_tok, output_tokens=32),
            )

        return ModelResponse(
            content=f"Fixed {self._spec.case_id} in {path}.",
            usage=TokenUsage(input_tokens=in_tok, output_tokens=14),
        )


def build_scripted_benchmark_model(
    spec: BenchmarkCaseSpec,
    ablation: AblationConfig,
) -> Model:
    """ModelBuilder returning a deterministic scripted benchmark model."""
    return ScriptedBenchmarkModel(spec, ablation)
