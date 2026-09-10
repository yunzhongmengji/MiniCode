"""Tool for discovering regular files inside a workspace."""

import asyncio
import json

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.file_selection import DEFAULT_EXCLUDED_DIRECTORY_NAMES
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import (
    Workspace,
    WorkspaceFileLimitError,
    WorkspacePathError,
)

_DEFAULT_MAX_FILES = 1_000


class ListFilesArguments(ToolArguments):
    """Validated arguments accepted by file discovery."""

    path: str = Field(
        default=".",
        description=("File or directory to list, relative to the workspace root."),
    )

    @field_validator("path")
    @classmethod
    def validate_path_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject blank paths."""
        if not value.strip():
            raise ValueError("path must not be blank")

        return value


_LIST_FILES_SPEC = ToolSpec(
    name="list_files",
    description=(
        "List project files under a workspace path in stable order, excluding "
        "common generated and dependency directories."
    ),
    arguments_type=ListFilesArguments,
)


class ListFilesTool:
    """Expose bounded workspace file discovery to the model."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_files: int = _DEFAULT_MAX_FILES,
    ) -> None:
        if isinstance(max_files, bool) or not isinstance(max_files, int):
            raise TypeError("max_files must be an integer")

        if max_files <= 0:
            raise ValueError("max_files must be greater than zero")

        self._workspace = workspace
        self._max_files = max_files

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _LIST_FILES_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """List regular files below one workspace path."""
        if not isinstance(arguments, ListFilesArguments):
            raise TypeError("arguments must be ListFilesArguments")

        try:
            paths = await asyncio.to_thread(
                self._workspace.list_files,
                arguments.path,
                max_files=self._max_files,
                excluded_directory_names=DEFAULT_EXCLUDED_DIRECTORY_NAMES,
            )
        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot list files outside the workspace: {arguments.path}"
            ) from error
        except WorkspaceFileLimitError as error:
            raise ToolExecutionError(
                f"file listing exceeds {self._max_files}-file limit: {arguments.path}"
            ) from error
        except FileNotFoundError as error:
            raise ToolExecutionError(
                f"list path not found: {arguments.path}"
            ) from error

        rendered_path = json.dumps(
            arguments.path,
            ensure_ascii=False,
        )

        if not paths:
            return f"No files found under {rendered_path}."

        return f"Files under {rendered_path}:\n" + "\n".join(paths)
