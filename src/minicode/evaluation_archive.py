"""Persist one validated formal context experiment without overwriting evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from minicode.evaluation_summary import summarize_context_experiment_results


@dataclass(frozen=True, slots=True)
class FormalArchiveResult:
    """The durable location and reproduced summary of one formal batch."""

    archive_root: Path
    source_file_count: int
    summary: str


def archive_formal_experiment(
    *,
    source_root: Path,
    archive_root: Path,
    protocol_path: Path,
) -> FormalArchiveResult:
    """Validate, copy, revalidate, and atomically publish one formal archive."""
    source = source_root.resolve(strict=True)
    protocol = protocol_path.resolve(strict=True)
    target = validate_formal_archive_target(
        archive_root=archive_root,
        source_root=source,
    )
    target_parent = target.parent

    source_summary = summarize_context_experiment_results(source, protocol)
    source_files = _build_file_manifest(source)

    with tempfile.TemporaryDirectory(
        dir=target_parent,
        prefix=f".{target.name}-staging-",
    ) as temporary_directory:
        staged = Path(temporary_directory) / target.name
        shutil.copytree(source, staged)
        copied_files = _build_file_manifest(staged)

        if copied_files != source_files:
            raise ValueError("formal archive copy disagrees with source file hashes")

        archived_summary = summarize_context_experiment_results(staged, protocol)

        if archived_summary != source_summary:
            raise ValueError("formal archive summary disagrees with source summary")

        report_path = staged / "REPORT.md"
        report_bytes = f"{archived_summary}\n".encode()
        report_path.write_bytes(report_bytes)
        _write_json_exclusively(
            staged / "ARCHIVE_MANIFEST.json",
            {
                "schema_version": 1,
                "source_file_count": len(source_files),
                "source_files": source_files,
                "report": {
                    "file": report_path.name,
                    "byte_count": len(report_bytes),
                    "sha256": hashlib.sha256(report_bytes).hexdigest(),
                },
            },
        )
        os.replace(staged, target)

    return FormalArchiveResult(
        archive_root=target,
        source_file_count=len(source_files),
        summary=source_summary,
    )


def validate_formal_archive_target(
    *,
    archive_root: Path,
    source_root: Path | None = None,
) -> Path:
    """Validate a new archive target before any Provider calls begin."""
    target = archive_root.resolve(strict=False)
    target.parent.resolve(strict=True)

    if target.name in {"", ".", ".."}:
        raise ValueError("formal archive root must name a new directory")

    if target.exists():
        raise FileExistsError(target)

    if source_root is not None:
        source = source_root.resolve(strict=False)

        if target == source or target.is_relative_to(source):
            raise ValueError("formal archive root must be outside the source results")

    return target


def _build_file_manifest(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []

    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"formal evidence must not contain symlinks: {path}")

        if path.is_dir():
            continue

        if not path.is_file():
            raise ValueError(f"formal evidence contains an unsupported entry: {path}")

        content = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "byte_count": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    if not files:
        raise ValueError("formal evidence must contain files")

    return files


def _write_json_exclusively(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the non-overwriting formal archive CLI parser."""
    parser = argparse.ArgumentParser(
        description="Validate and persist one formal context experiment.",
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Archive one completed formal experiment and report the durable path."""
    args = build_parser().parse_args(argv)

    try:
        result = archive_formal_experiment(
            source_root=args.source_root,
            archive_root=args.archive_root,
            protocol_path=args.protocol,
        )
    except (OSError, TypeError, ValueError) as error:
        print(f"Formal archive error: {error}", file=sys.stderr)
        return 2

    print(result.summary)
    print(f"Archived {result.source_file_count} source files to {result.archive_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
