"""Prepare an isolated Git workspace for one evaluation case."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from minicode.evaluation_case import load_case_manifest


def prepare_evaluation_workspace(
    case_root: Path,
    *,
    temporary_root: Path | None = None,
) -> Path:
    """Copy a case workspace and commit its initial Git baseline."""
    resolved_case_root = case_root.resolve(strict=True)
    manifest = load_case_manifest(resolved_case_root)
    source_workspace = (resolved_case_root / "workspace").resolve(
        strict=True,
    )
    resolved_temporary_root = (
        None if temporary_root is None else temporary_root.resolve(strict=True)
    )
    destination = Path(
        tempfile.mkdtemp(
            prefix=f"minicode-eval-{manifest.case_id}.",
            dir=resolved_temporary_root,
        )
    )

    shutil.copytree(
        source_workspace,
        destination,
        dirs_exist_ok=True,
    )
    _run_git(destination, "init", "-q")
    _run_git(destination, "add", ".")
    _run_git(
        destination,
        "-c",
        "user.name=MiniCode Evaluation",
        "-c",
        "user.email=evaluation@example.invalid",
        "commit",
        "-q",
        "-m",
        "evaluation baseline",
    )
    return destination


def _run_git(
    workspace: Path,
    *arguments: str,
) -> None:
    """Run one fixed Git preparation command."""
    subprocess.run(
        (
            "git",
            *arguments,
        ),
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the workspace-preparation argument parser."""
    parser = argparse.ArgumentParser(
        description="Prepare an isolated MiniCode evaluation workspace.",
    )
    parser.add_argument(
        "--case-root",
        type=Path,
        required=True,
        help="Evaluation case containing case.json and workspace/.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare one workspace and print its path."""
    args = build_parser().parse_args(argv)
    workspace = prepare_evaluation_workspace(args.case_root)
    print(workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
