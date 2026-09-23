from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import minicode.evaluation_archive as archive_module
from minicode.evaluation_archive import archive_formal_experiment


def _write_source(root: Path) -> dict[str, bytes]:
    files = {
        "protocol.snapshot.json": b'{"protocol_id":"test"}\n',
        "formal-plan.json": b'{"runs":[]}\n',
        "formal-events.jsonl": b'{"event":"run_started"}\n',
        "01-case-baseline/answer.txt": b"done\n",
        "01-case-baseline/trace.txt": b"Trace run_test\n",
        "01-case-baseline/workspace.patch": b"",
        "01-case-baseline/result.json": b'{"accepted":true}\n',
    }

    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    return files


def test_formal_archive_copies_every_file_and_reproduces_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_files = _write_source(source)
    protocol = tmp_path / "protocol.json"
    protocol.write_text('{"protocol_id":"test"}\n', encoding="utf-8")
    archive = tmp_path / "archive"
    summary_calls: list[Path] = []

    def _fake_summary(results_root: Path, protocol_path: Path) -> str:
        summary_calls.append(results_root)
        assert protocol_path == protocol
        assert (results_root / "formal-plan.json").is_file()
        return "- Advancement gate: FAIL"

    monkeypatch.setattr(
        archive_module,
        "summarize_context_experiment_results",
        _fake_summary,
    )

    result = archive_formal_experiment(
        source_root=source,
        archive_root=archive,
        protocol_path=protocol,
    )

    assert result.archive_root == archive
    assert result.source_file_count == len(source_files)
    assert result.summary == "- Advancement gate: FAIL"
    assert summary_calls[0] == source
    assert summary_calls[1].parent != tmp_path
    for relative_path, content in source_files.items():
        assert (archive / relative_path).read_bytes() == content
    assert (archive / "REPORT.md").read_text(encoding="utf-8") == (
        "- Advancement gate: FAIL\n"
    )
    manifest = json.loads(
        (archive / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["source_file_count"] == len(source_files)
    assert {entry["path"] for entry in manifest["source_files"]} == set(source_files)
    assert (
        manifest["report"]["sha256"]
        == hashlib.sha256(b"- Advancement gate: FAIL\n").hexdigest()
    )


def test_formal_archive_never_overwrites_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}\n", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    sentinel = archive / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        archive_module,
        "summarize_context_experiment_results",
        lambda *_: (_ for _ in ()).throw(AssertionError("summary called")),
    )

    with pytest.raises(FileExistsError):
        archive_formal_experiment(
            source_root=source,
            archive_root=archive,
            protocol_path=protocol,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_formal_archive_does_not_publish_mismatched_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_files = _write_source(source)
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}\n", encoding="utf-8")
    archive = tmp_path / "archive"
    summaries = iter(("source summary", "different copied summary"))
    monkeypatch.setattr(
        archive_module,
        "summarize_context_experiment_results",
        lambda *_: next(summaries),
    )

    with pytest.raises(ValueError, match="summary disagrees"):
        archive_formal_experiment(
            source_root=source,
            archive_root=archive,
            protocol_path=protocol,
        )

    assert not archive.exists()
    for relative_path, content in source_files.items():
        assert (source / relative_path).read_bytes() == content
