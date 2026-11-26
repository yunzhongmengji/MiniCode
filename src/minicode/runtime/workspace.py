"""Filesystem boundary for files managed by MiniCode."""

import os
import stat
import tempfile
from pathlib import Path


class WorkspacePathError(PermissionError):
    """Raised when a requested path escapes the workspace."""


class WorkspaceReadLimitError(OSError):
    """Raised when a file exceeds the configured read limit."""

    def __init__(
        self,
        max_bytes: int,
    ) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"file exceeds {max_bytes}-byte read limit")


class WorkspaceFileLimitError(OSError):
    """Raised when a directory contains too many searchable files."""

    def __init__(
        self,
        max_files: int,
    ) -> None:
        self.max_files = max_files
        super().__init__(f"search exceeds {max_files}-file limit")


class Workspace:
    """Provide filesystem operations rooted at one directory."""

    def __init__(
        self,
        root: Path,
    ) -> None:
        resolved_root = root.resolve(strict=True)

        if not resolved_root.is_dir():
            raise NotADirectoryError("workspace root must be a directory")

        self._root = resolved_root

    @property
    def root(self) -> Path:
        """Return the resolved workspace root."""
        return self._root

    def resolve_path(
        self,
        relative_path: str,
    ) -> Path:
        """Resolve a path through the workspace boundary."""
        return self._resolve(relative_path)

    def read_text(
        self,
        relative_path: str,
        *,
        max_bytes: int | None = None,
    ) -> str:
        """Read one UTF-8 text file from the workspace."""
        if max_bytes is not None:
            if isinstance(max_bytes, bool) or not isinstance(
                max_bytes,
                int,
            ):
                raise TypeError("max_bytes must be an integer or None")

            if max_bytes <= 0:
                raise ValueError("max_bytes must be greater than zero")

        file_path = self._resolve(relative_path)

        if max_bytes is None:
            return file_path.read_text(
                encoding="utf-8",
            )

        with file_path.open("rb") as file:
            content = file.read(max_bytes + 1)

        if len(content) > max_bytes:
            raise WorkspaceReadLimitError(max_bytes)

        return content.decode("utf-8")

    def write_text(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        """Atomically write UTF-8 text to an existing workspace file."""
        if not isinstance(
            content,
            str,
        ):
            raise TypeError("content must be a string")

        file_path = self._resolve(relative_path)

        if not file_path.exists():
            raise FileNotFoundError(f"path does not exist: {relative_path}")

        if not file_path.is_file():
            raise IsADirectoryError(f"path is not a file: {relative_path}")

        file_mode = stat.S_IMODE(file_path.stat().st_mode)

        with tempfile.TemporaryDirectory(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
        ) as temporary_directory:
            temporary_path = Path(temporary_directory) / file_path.name

            temporary_path.write_text(
                content,
                encoding="utf-8",
            )

            os.chmod(
                temporary_path,
                file_mode,
            )

            os.replace(
                temporary_path,
                file_path,
            )

    def create_text(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        """Atomically create a UTF-8 file without overwriting an existing path."""
        if not isinstance(content, str):
            raise TypeError("content must be a string")

        file_path = self._resolve(relative_path)

        with tempfile.TemporaryDirectory(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
        ) as temporary_directory:
            temporary_path = Path(temporary_directory) / file_path.name
            temporary_path.write_text(
                content,
                encoding="utf-8",
            )

            os.link(
                temporary_path,
                file_path,
            )

    def list_files(
        self,
        relative_path: str,
        *,
        max_files: int,
        excluded_directory_names: frozenset[str] = frozenset(),
    ) -> tuple[str, ...]:
        """List a bounded number of regular workspace files."""
        if isinstance(
            max_files,
            bool,
        ) or not isinstance(
            max_files,
            int,
        ):
            raise TypeError("max_files must be an integer")

        if max_files <= 0:
            raise ValueError("max_files must be greater than zero")

        target_path = self._resolve(relative_path)

        if target_path.is_file():
            candidate_paths: tuple[Path, ...] = (target_path,)
        elif target_path.is_dir():
            collected_paths: list[Path] = []

            for directory_path, directory_names, file_names in target_path.walk():
                directory_names[:] = sorted(
                    name
                    for name in directory_names
                    if name not in excluded_directory_names
                )

                for file_name in sorted(file_names):
                    path = directory_path / file_name

                    if not path.is_file():
                        continue

                    if len(collected_paths) >= max_files:
                        raise WorkspaceFileLimitError(max_files)

                    collected_paths.append(path)

            candidate_paths = tuple(collected_paths)
        else:
            raise FileNotFoundError(f"path does not exist: {relative_path}")

        return tuple(
            sorted(path.relative_to(self._root).as_posix() for path in candidate_paths)
        )

    def _resolve(
        self,
        relative_path: str,
    ) -> Path:
        """Resolve a path and reject access outside the workspace."""
        candidate = (self._root / relative_path).resolve(
            strict=False,
        )

        if not candidate.is_relative_to(self._root):
            raise WorkspacePathError("path escapes workspace")

        return candidate
