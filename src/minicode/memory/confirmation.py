"""Host-terminal confirmation of one source-checked test-target candidate."""

import json
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from minicode.memory.test_target import TestTargetCandidate, load_test_target_candidate
from minicode.workspace import Workspace

MAX_APPLIES_TO_CHARS = 500


class TestTargetConfirmation(BaseModel):
    """Host confirmation data, not an unforgeable token or execution permission."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate: TestTargetCandidate
    applies_to: str = Field(min_length=1, max_length=MAX_APPLIES_TO_CHARS)

    @field_validator("applies_to")
    @classmethod
    def require_normalized_scope(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("applies_to must be nonblank and trimmed")
        return value


def confirm_test_target(
    *,
    workspace: Workspace,
    state_home: Path,
    run_id: str,
    call_id: str,
    input_reader: Callable[[], str] = input,
) -> TestTargetConfirmation | None:
    """Ask the host user, re-read the source, and return data without saving it.

    The normal input reader requires a terminal. Reader injection is for trusted
    host code/tests, never a model-controlled approval endpoint. The candidate
    comparison covers its six fields, not all history or project file contents.
    """
    if input_reader is input and not sys.stdin.isatty():
        raise ValueError("test-target confirmation requires an interactive terminal")
    candidate = load_test_target_candidate(
        workspace=workspace, state_home=state_home, run_id=run_id, call_id=call_id
    )
    print(
        "测试目标候选（尚未保存）：\n"
        + json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n这只说明历史调用未报错，不证明覆盖完整或以后仍会通过。"
        + f"\n请填写适用范围（1–{MAX_APPLIES_TO_CHARS} 个字符）：",
        end="",
        file=sys.stderr,
        flush=True,
    )
    try:
        scope = input_reader()
        if not isinstance(scope, str):
            raise TypeError("input reader must return a string")
        scope = scope.strip()
        if not scope or len(scope) > MAX_APPLIES_TO_CHARS:
            raise ValueError(
                "applicability scope must contain 1–500 trimmed characters"
            )
        print(
            "\n适用范围："
            + json.dumps(scope, ensure_ascii=False)
            + "\n确认采纳这条候选及上述范围？[y/N]：",
            end="",
            file=sys.stderr,
            flush=True,
        )
        answer = input_reader()
        if not isinstance(answer, str):
            raise TypeError("input reader must return a string")
    except (EOFError, KeyboardInterrupt):
        return None
    if answer.strip().casefold() not in {"y", "yes"}:
        return None
    current = load_test_target_candidate(
        workspace=workspace, state_home=state_home, run_id=run_id, call_id=call_id
    )
    if current != candidate:
        raise ValueError("test-target source changed during confirmation; review again")
    return TestTargetConfirmation(candidate=current, applies_to=scope)
