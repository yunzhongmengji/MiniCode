"""Tool for reading UTF-8 text files from a workspace."""

import asyncio
import json

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import (
    Workspace,
    WorkspacePathError,
    WorkspaceReadLimitError,
)

_DEFAULT_MAX_BYTES = 100_000


class ReadFileArguments(ToolArguments):
    """Validated arguments accepted by the read-file tool."""

    path: str = Field(
        description=("Path to a UTF-8 text file, relative to the workspace root."),
    )

    @field_validator("path")
    @classmethod
    def validate_path_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject paths containing only whitespace."""
        if not value.strip():
            raise ValueError("path must not be blank")

        return value


_READ_FILE_SPEC = ToolSpec(
    name="read_file",
    description=(
        "Read a UTF-8 text file from the workspace and return path-labeled content."
    ),
    arguments_type=ReadFileArguments,
)


class ReadFileTool:
    """Read text files through the workspace security boundary."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(
            max_bytes,
            int,
        ):
            raise TypeError("max_bytes must be an integer")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        self._workspace = workspace
        self._max_bytes = max_bytes

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _READ_FILE_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Read and return one validated workspace file."""
        if not isinstance(arguments, ReadFileArguments):
            raise TypeError("arguments must be ReadFileArguments")

        try:
            content = await asyncio.to_thread(
                self._workspace.read_text,
                arguments.path,
                max_bytes=self._max_bytes,
            )
        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot read '{arguments.path}': path is outside the workspace"
            ) from error
        except WorkspaceReadLimitError as error:
            raise ToolExecutionError(
                f"file exceeds {self._max_bytes}-byte read limit: {arguments.path}"
            ) from error
        except PermissionError as error:
            raise ToolExecutionError(f"permission denied: {arguments.path}") from error
        except FileNotFoundError as error:
            raise ToolExecutionError(f"file not found: {arguments.path}") from error
        except IsADirectoryError as error:
            raise ToolExecutionError(f"path is not a file: {arguments.path}") from error
        except UnicodeDecodeError as error:
            raise ToolExecutionError(
                f"file is not valid UTF-8: {arguments.path}"
            ) from error

        rendered_path = json.dumps(
            arguments.path,
            ensure_ascii=False,
        )
        return f"File {rendered_path}:\n{content}"
