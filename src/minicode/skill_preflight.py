"""One frozen, fresh-run Skill pair; preparation never calls a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from contextlib import chdir, redirect_stderr, redirect_stdout
from importlib.metadata import version
from io import StringIO
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from minicode import cli
from minicode.core.model import ModelRunBudget
from minicode.core.tool_calls import ToolCall
from minicode.evaluation_case import load_case_manifest
from minicode.evaluation_preflight_executor import extract_evaluation_trace
from minicode.evaluation_prepare import prepare_evaluation_workspace
from minicode.evaluation_result import record_result
from minicode.evaluation_run import build_coding_run_arguments
from minicode.models.dashscope import DashScopeConfig
from minicode.workspace import Workspace, WorkspacePathError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXPERIMENT = Path("benchmarks/skill_task_comparison/v1")
_CASE = Path("benchmarks/coding_agent/cases/multi_file_inventory_contract")


class SkillPreflightProtocol(BaseModel):
    """Validate the fixture-specific plan, not a general experiment framework."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1]
    protocol_id: str = Field(min_length=1)
    case_id: Literal["multi_file_inventory_contract"]
    model: str = Field(min_length=1)
    base_url: Literal["https://dashscope.aliyuncs.com/compatible-mode/v1"]
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_response_output_tokens: int = Field(gt=0)
    max_turns: Literal[8]
    max_tool_calls: Literal[8]
    model_max_retries: Literal[0]
    temperature: float = Field(ge=0, le=0)
    enable_thinking: Literal[False]
    arm_order: tuple[Literal["baseline"], Literal["treatment"]]
    allowed_edit_paths: tuple[Literal["inventory.py"], Literal["report.py"]]
    allowed_test_paths: tuple[
        Literal["tests"], Literal["tests/test_inventory_contract.py"]
    ]
    expected_skill_names: tuple[Literal["inventory-contract-review"]]

    def token_budget(self) -> ModelRunBudget:
        return ModelRunBudget(
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_response_output_tokens,
        )


class FixtureToolApprover:
    """Approve only this isolated case's edits and fixed pytest targets."""

    def __init__(self, workspace: Path, protocol: SkillPreflightProtocol) -> None:
        self._workspace = Workspace(workspace)
        self._protocol = protocol

    async def request_approval(self, call: ToolCall, *, reason: str) -> bool:
        path = call.arguments.get("path", "tests" if call.name == "run_tests" else None)
        if not isinstance(path, str):
            return False
        try:
            relative = (
                self._workspace.resolve_path(path)
                .relative_to(self._workspace.root)
                .as_posix()
            )
        except (OSError, ValueError, WorkspacePathError):
            return False
        return (
            call.name == "edit_file" and relative in self._protocol.allowed_edit_paths
        ) or (
            call.name == "run_tests" and relative in self._protocol.allowed_test_paths
        )


def _write_text(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _source_files(project_root: Path) -> tuple[Path, ...]:
    files = [*project_root.joinpath("src").rglob("*.py")]
    for directory in (_CASE, _EXPERIMENT / "skills"):
        files.extend(
            path
            for path in project_root.joinpath(directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    files.extend(project_root / name for name in ("pyproject.toml", "uv.lock"))
    files.append(project_root / _EXPERIMENT / "preflight.json")
    return tuple(sorted(path for path in files if path.is_file()))


def _hash_sources(project_root: Path) -> dict[str, str]:
    return {
        path.relative_to(project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in _source_files(project_root)
    }


def _verify_snapshot(project_root: Path, root: Path, expected: dict[str, str]) -> None:
    if _hash_sources(project_root) != expected:
        raise ValueError("source/case/Skill changed after preparation; batch stopped")
    for name, digest in expected.items():
        if (
            hashlib.sha256((root / "snapshot" / name).read_bytes()).hexdigest()
            != digest
        ):
            raise ValueError("prepared snapshot changed; batch stopped")


def prepare_skill_preflight(
    results_root: Path, *, project_root: Path = _PROJECT_ROOT
) -> Path:
    """Save a reviewable protocol and exact source bytes without any API call."""
    project_root = project_root.resolve(strict=True)
    root = results_root.resolve()
    if root.is_relative_to(project_root):
        raise ValueError("results_root must be outside the source repository")
    protocol = SkillPreflightProtocol.model_validate_json(
        (project_root / _EXPERIMENT / "preflight.json").read_text(encoding="utf-8")
    )
    protocol.token_budget()
    manifest = load_case_manifest(project_root / _CASE)
    if (
        manifest.allowed_changes != protocol.allowed_edit_paths
        or manifest.budget.max_turns != protocol.max_turns
        or manifest.budget.max_tool_calls != protocol.max_tool_calls
    ):
        raise ValueError("protocol disagrees with case permissions or budget")
    hashes = _hash_sources(project_root)
    root.mkdir(parents=True, exist_ok=False)
    for name in hashes:
        target = root / "snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write((project_root / name).read_bytes())
    _write_json(
        root / "plan.json",
        {
            "protocol": protocol.model_dump(mode="json"),
            "source_sha256": hashes,
            "source_root": str(project_root),
            "python": sys.version,
            "dependencies": {
                name: version(name) for name in ("openai", "pydantic", "pytest")
            },
            "max_model_requests": 16,
            "run_attempts_per_arm": 1,
            "cumulative_limits_are_post_response_thresholds": True,
        },
    )
    _verify_snapshot(project_root, root, hashes)
    return root


def _assert_provider(protocol: SkillPreflightProtocol) -> None:
    config = DashScopeConfig.from_environment(os.environ)
    if config.model != protocol.model or config.base_url != protocol.base_url:
        raise ValueError("configured model/base_url disagrees with frozen Skill plan")


def _assert_runtime(plan: dict[str, object]) -> None:
    if plan["python"] != sys.version or plan["dependencies"] != {
        name: version(name) for name in ("openai", "pydantic", "pytest")
    }:
        raise ValueError("Python/dependency versions changed after preparation")


def execute_skill_preflight(results_root: Path) -> bool:
    """Consume one prepared plan once, stopping before a second unsafe run."""
    root = results_root.resolve(strict=True)
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    project_root = Path(plan["source_root"]).resolve(strict=True)
    protocol = SkillPreflightProtocol.model_validate_json(json.dumps(plan["protocol"]))
    snapshot_protocol = SkillPreflightProtocol.model_validate_json(
        (root / "snapshot" / _EXPERIMENT / "preflight.json").read_text(encoding="utf-8")
    )
    if protocol != snapshot_protocol or project_root != _PROJECT_ROOT:
        raise ValueError(
            "prepared plan does not match snapshot or executing repository"
        )
    _verify_snapshot(project_root, root, plan["source_sha256"])
    _assert_runtime(plan)
    _assert_provider(protocol)
    # Exclusive marker prevents accidental retries even after a failed/interrupted run.
    _write_text(
        root / "execution.started", "one attempt per arm; do not resume or retry\n"
    )
    records: list[dict[str, object]] = []
    case_root = root / "snapshot" / _CASE
    skills_root = root / "snapshot" / _EXPERIMENT / "skills"
    for arm in protocol.arm_order:
        print(f"Skill Preflight: {arm} (one attempt)", flush=True)
        directory = root / arm
        directory.mkdir()
        stdout, stderr = StringIO(), StringIO()
        try:
            _verify_snapshot(project_root, root, plan["source_sha256"])
            _assert_runtime(plan)
            _assert_provider(protocol)
            workspace = prepare_evaluation_workspace(case_root, temporary_root=root)
            _write_text(directory / "workspace.path", str(workspace) + "\n")
            with chdir(workspace), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(
                    build_coding_run_arguments(
                        case_root,
                        skills_root=skills_root if arm == "treatment" else None,
                    ),
                    expected_model=protocol.model,
                    model_max_retries=protocol.model_max_retries,
                    model_budget=protocol.token_budget(),
                    approver=FixtureToolApprover(workspace, protocol),
                )
            _write_text(directory / "answer.txt", stdout.getvalue())
            _write_text(directory / "stderr.txt", stderr.getvalue())
            _write_text(
                directory / "trace.txt", extract_evaluation_trace(stderr.getvalue())
            )
            record_result(
                case_root=case_root,
                workspace=workspace,
                answer_path=directory / "answer.txt",
                trace_path=directory / "trace.txt",
                output_path=directory / "result.json",
                model=protocol.model,
                agent_exit_code=exit_code,
                skill_arm=arm,
            )
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            run = result["run"]
            expected_budget = {
                "max_input_tokens": protocol.max_input_tokens,
                "max_output_tokens": protocol.max_output_tokens,
                "max_response_output_tokens": protocol.max_response_output_tokens,
                "require_complete_usage": True,
            }
            expected_skills = (
                [] if arm == "baseline" else list(protocol.expected_skill_names)
            )
            comparable = (
                exit_code == 0
                and run["stop_reason"] == "completed"
                and run["usage_complete"] is True
                and run.get("model_budget") == expected_budget
                and run["input_tokens"] < protocol.max_input_tokens
                and run["output_tokens"] < protocol.max_output_tokens
                and run["model_call_count"] <= protocol.max_turns
                and run["tool_execution_count"] <= protocol.max_tool_calls
                and result["skill_experiment"]["selected_skill_names"]
                == expected_skills
                and result["skill_experiment"]["loaded_skill_names"] == expected_skills
            )
            _verify_snapshot(project_root, root, plan["source_sha256"])
            records.append(
                {
                    "arm": arm,
                    "comparable": comparable,
                    "task_passed": result["verdict"]["passed"],
                    "run": run,
                }
            )
            _write_json(directory / "run-summary.json", records[-1])
            if not comparable:
                break
        except (OSError, ValueError, TypeError, RuntimeError, KeyError) as error:
            records.append(
                {
                    "arm": arm,
                    "comparable": False,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            # Keep raw stdout/stderr even if extraction or recording failed.
            if not (directory / "answer.txt").exists():
                _write_text(directory / "answer.txt", stdout.getvalue())
                _write_text(directory / "stderr.txt", stderr.getvalue())
            _write_json(directory / "failure.json", records[-1])
            break
    report = _batch_report(protocol, records)
    _write_json(root / "batch.json", report)
    print(f"Pair complete: {report['pair_complete']}; evidence: {root}")
    return report["pair_complete"] is True


def _batch_report(
    protocol: SkillPreflightProtocol, records: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "protocol_id": protocol.protocol_id,
        "pair_complete": len(records) == 2
        and all(r["comparable"] is True for r in records),
        "runs": records,
        "conclusion_scope": "single-case Preflight, not a success-rate improvement claim",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--prepare", action="store_true", help="Offline: freeze a new plan."
    )
    actions.add_argument(
        "--execute", action="store_true", help="Paid: consume a prepared plan once."
    )
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            print(prepare_skill_preflight(args.results_root))
            return 0
        return 0 if execute_skill_preflight(args.results_root) else 1
    except (OSError, ValueError) as error:
        print(f"Skill Preflight error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
