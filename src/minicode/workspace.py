"""Filesystem boundary for files managed by MiniCode."""

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
