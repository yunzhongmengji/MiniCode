"""Execute one registered Preflight arm through the existing CLI boundaries."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Protocol, TextIO

from minicode.context_experiment_protocol import (
    BudgetedContextExperimentProtocol,
    load_budgeted_context_experiment_protocol,
)
from minicode.evaluation_preflight import PreflightRunRequest
from minicode.evaluation_prepare import prepare_evaluation_workspace
from minicode.evaluation_run import EvaluationArm


@dataclass(frozen=True, slots=True)
class EvaluationCommandResult:
    """Captured outcome of one evaluation subprocess."""

    returncode: int
    stdout: str
    stderr: str


class EvaluationCommandRunner(Protocol):
    """Run one command so the real subprocess boundary can be replaced in tests."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
    ) -> EvaluationCommandResult:
        """Execute one command and capture its output."""


class StreamingSubprocessCommandRunner:
    """Capture command output while keeping approval prompts visible."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
    ) -> EvaluationCommandResult:
        """Run with inherited stdin and stream stderr to the current terminal."""
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        if process.stdout is None or process.stderr is None:
            process.kill()
            raise RuntimeError("evaluation subprocess pipes were not created")

        stderr_chunks: list[str] = []
        stderr_thread = Thread(
            target=_drain_visible_stderr,
            args=(process.stderr, stderr_chunks),
            daemon=True,
        )
        stderr_thread.start()
        stdout = process.stdout.read()
        returncode = process.wait()
        stderr_thread.join()
        return EvaluationCommandResult(
            returncode=returncode,
            stdout=stdout,
            stderr="".join(stderr_chunks),
        )


class ContextPreflightCommandExecutor:
    """Prepare, run, extract, and record one context experiment arm."""

    def __init__(
        self,
        *,
        project_root: Path,
        temporary_root: Path | None = None,
        command_runner: EvaluationCommandRunner | None = None,
        python_executable: str = sys.executable,
    ) -> None:
        self._project_root = project_root.resolve(strict=True)
        self._temporary_root = (
            None
            if temporary_root is None
            else temporary_root.resolve(strict=True)
        )
        self._command_runner = (
            StreamingSubprocessCommandRunner()
            if command_runner is None
            else command_runner
        )

        if not python_executable.strip():
            raise ValueError("python_executable must not be blank")

        self._python_executable = python_executable

    def validate_environment(self, results_root: Path) -> None:
        """Reject an unsafe batch before its results directory is created."""
        _assert_clean_repository(self._project_root)
        _assert_new_results_root_outside_repository(
            results_root,
            self._project_root,
        )

    def execute(self, request: PreflightRunRequest) -> bool:
        """Execute one frozen arm and leave all diagnostic artifacts on disk."""
        _assert_results_outside_repository(
            request.result_directory,
            self._project_root,
        )
        _assert_clean_repository(self._project_root)
        protocol = load_budgeted_context_experiment_protocol(
            request.protocol_snapshot_path
        )
        arm = _validate_request_against_protocol(request, protocol)
        case_root = (
            self._project_root
            / "benchmarks"
            / "coding_agent"
            / "cases"
            / request.case_id
        ).resolve(strict=True)
        workspace = prepare_evaluation_workspace(
            case_root,
            temporary_root=self._temporary_root,
        )
        _write_text_exclusively(
            request.result_directory / "workspace.path.txt",
            f"{workspace}\n",
        )

        agent_result = self._command_runner.run(
            (
                self._python_executable,
                "-m",
                "minicode.evaluation_run",
                "--case-root",
                str(case_root),
                "--context-protocol",
                str(request.protocol_snapshot_path),
                "--arm",
                arm.value,
            ),
            cwd=workspace,
        )
        answer_path = request.result_directory / "answer.txt"
        stderr_path = request.result_directory / "stderr.raw.txt"
        _write_text_exclusively(answer_path, agent_result.stdout)
        _write_text_exclusively(stderr_path, agent_result.stderr)

        try:
            trace = extract_evaluation_trace(agent_result.stderr)
        except ValueError:
            return False

        trace_path = request.result_directory / "trace.txt"
        _write_text_exclusively(trace_path, trace)
        result_path = request.result_directory / "result.json"
        recorder_result = self._command_runner.run(
            (
                self._python_executable,
                "-m",
                "minicode.evaluation_result",
                "--case-root",
                str(case_root),
                "--workspace",
                str(workspace),
                "--answer",
                str(answer_path),
                "--trace",
                str(trace_path),
                "--output",
                str(result_path),
                "--model",
                protocol.model.name,
                "--agent-exit-code",
                str(agent_result.returncode),
                "--context-protocol",
                str(request.protocol_snapshot_path),
                "--context-arm",
                arm.value,
            ),
            cwd=self._project_root,
        )
        _write_text_exclusively(
            request.result_directory / "result-recorder.stdout.txt",
            recorder_result.stdout,
        )
        _write_text_exclusively(
            request.result_directory / "result-recorder.stderr.txt",
            recorder_result.stderr,
        )
        return recorder_result.returncode == 0


def extract_evaluation_trace(stderr: str) -> str:
    """Extract the one canonical Trace suffix from mixed CLI stderr."""
    marker = "Trace run_"
    marker_count = stderr.count(marker)

    if marker_count != 1:
        raise ValueError(
            "evaluation stderr must contain exactly one 'Trace run_' marker"
        )

    marker_index = stderr.index(marker)
    trace = stderr[marker_index:]
    return trace if trace.endswith("\n") else f"{trace}\n"


def _validate_request_against_protocol(
    request: PreflightRunRequest,
    protocol: BudgetedContextExperimentProtocol,
) -> EvaluationArm:
    if request.protocol_id != protocol.protocol_id:
        raise ValueError("Preflight request protocol_id disagrees with snapshot")

    if request.case_id != protocol.preflight_plan.case_id:
        raise ValueError("Preflight request case disagrees with snapshot")

    try:
        arm = EvaluationArm(request.arm)
    except ValueError as error:
        raise ValueError("Preflight request contains an unknown arm") from error

    if not 1 <= request.run_index <= len(protocol.preflight_plan.arm_order):
        raise ValueError("Preflight request run_index is outside the plan")

    expected_arm = protocol.preflight_plan.arm_order[request.run_index - 1]

    if arm.value != expected_arm:
        raise ValueError("Preflight request order disagrees with snapshot")

    return arm


def _assert_clean_repository(project_root: Path) -> None:
    repository_root = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if Path(repository_root).resolve(strict=True) != project_root:
        raise ValueError("project_root must be the Git repository root")

    status = subprocess.run(
        ("git", "status", "--short"),
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    if status:
        raise ValueError(
            "registered Preflight requires a clean MiniCode repository"
        )


def _assert_results_outside_repository(
    result_directory: Path,
    project_root: Path,
) -> None:
    resolved_result = result_directory.resolve(strict=True)

    if resolved_result.is_relative_to(project_root):
        raise ValueError(
            "Preflight results must be created outside the MiniCode repository"
        )


def _assert_new_results_root_outside_repository(
    results_root: Path,
    project_root: Path,
) -> None:
    """Validate one prospective batch root without creating it."""
    resolved_result = results_root.resolve(strict=False)

    if resolved_result.is_relative_to(project_root):
        raise ValueError(
            "Preflight results must be created outside the MiniCode repository"
        )

    if results_root.exists():
        raise FileExistsError(results_root)


def _drain_visible_stderr(stream: TextIO, chunks: list[str]) -> None:
    while character := stream.read(1):
        chunks.append(character)
        sys.stderr.write(character)
        sys.stderr.flush()


def _write_text_exclusively(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)
