from pathlib import Path

import pytest

from minicode.workspace import (
    Workspace,
    WorkspacePathError,
    WorkspaceReadLimitError,
)


def test_workspace_reads_utf8_file_inside_root(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text(
        "MiniCode workspace",
        encoding="utf-8",
    )
    workspace = Workspace(
        root=tmp_path,
    )

    content = workspace.read_text("README.md")

    assert content == "MiniCode workspace"


def test_workspace_rejects_parent_path_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret",
        encoding="utf-8",
    )

    workspace = Workspace(
        root=workspace_root,
    )

    with pytest.raises(
        WorkspacePathError,
        match="path escapes workspace",
    ):
        workspace.read_text("../secret.txt")


def test_workspace_rejects_absolute_path(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret",
        encoding="utf-8",
    )

    workspace = Workspace(
        root=workspace_root,
    )

    with pytest.raises(
        WorkspacePathError,
        match="path escapes workspace",
    ):
        workspace.read_text(str(outside_file))


def test_workspace_rejects_symlink_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret",
        encoding="utf-8",
    )

    link_path = workspace_root / "linked-secret.txt"
    link_path.symlink_to(outside_file)

    workspace = Workspace(
        root=workspace_root,
    )

    with pytest.raises(
        WorkspacePathError,
        match="path escapes workspace",
    ):
        workspace.read_text("linked-secret.txt")


def test_workspace_rejects_file_as_root(
    tmp_path: Path,
) -> None:
    file_root = tmp_path / "not-a-directory.txt"
    file_root.write_text(
        "content",
        encoding="utf-8",
    )

    with pytest.raises(
        NotADirectoryError,
        match="workspace root must be a directory",
    ):
        Workspace(
            root=file_root,
        )


def test_workspace_reads_file_at_byte_limit(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "exact.txt"
    file_path.write_bytes(b"12345")
    workspace = Workspace(
        root=tmp_path,
    )

    content = workspace.read_text(
        "exact.txt",
        max_bytes=5,
    )

    assert content == "12345"


def test_workspace_rejects_file_over_byte_limit(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "large.txt"
    file_path.write_bytes(b"123456")
    workspace = Workspace(
        root=tmp_path,
    )

    with pytest.raises(
        WorkspaceReadLimitError,
        match="file exceeds 5-byte read limit",
    ) as exc_info:
        workspace.read_text(
            "large.txt",
            max_bytes=5,
        )

    assert exc_info.value.max_bytes == 5


@pytest.mark.parametrize(
    "max_bytes",
    [
        True,
        1.5,
        "5",
    ],
)
def test_workspace_rejects_non_integer_byte_limit(
    tmp_path: Path,
    max_bytes: object,
) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text(
        "content",
        encoding="utf-8",
    )
    workspace = Workspace(
        root=tmp_path,
    )

    with pytest.raises(
        TypeError,
        match="max_bytes must be an integer or None",
    ):
        workspace.read_text(
            "file.txt",
            max_bytes=max_bytes,
        )


@pytest.mark.parametrize(
    "max_bytes",
    [
        0,
        -1,
    ],
)
def test_workspace_rejects_non_positive_byte_limit(
    tmp_path: Path,
    max_bytes: int,
) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text(
        "content",
        encoding="utf-8",
    )
    workspace = Workspace(
        root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="max_bytes must be greater than zero",
    ):
        workspace.read_text(
            "file.txt",
            max_bytes=max_bytes,
        )
