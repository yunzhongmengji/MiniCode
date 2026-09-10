"""Tool for creating new UTF-8 files inside a workspace."""

import asyncio
import json

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import Workspace, WorkspacePathError

_DEFAULT_MAX_BYTES = 100_000


class CreateFileArguments(ToolArguments):
    """Validated arguments accepted by file creation."""

    path: str = Field(
        description=("New file path, relative to the workspace root."),
    )
    content: str = Field(
        description=("Complete UTF-8 text content for the new file."),
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


_CREATE_FILE_SPEC = ToolSpec(
    name="create_file",
    description=("Create a new UTF-8 text file without overwriting an existing path."),
    arguments_type=CreateFileArguments,
)


class CreateFileTool:
    """Create one bounded text file without replacement."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        self._workspace = workspace
        self._max_bytes = max_bytes

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _CREATE_FILE_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Create a new workspace file from complete text content."""
        if not isinstance(arguments, CreateFileArguments):
            raise TypeError("arguments must be CreateFileArguments")

        content_size = len(arguments.content.encode("utf-8"))

        if content_size > self._max_bytes:
            raise ToolExecutionError(
                f"new file exceeds {self._max_bytes}-byte creation limit: "
                f"{arguments.path}"
            )

        try:
            await asyncio.to_thread(
                self._workspace.create_text,
                arguments.path,
                arguments.content,
            )
        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot create '{arguments.path}': path is outside the workspace"
            ) from error
        except FileExistsError as error:
            raise ToolExecutionError(
                f"file already exists: {arguments.path}"
            ) from error
        except FileNotFoundError as error:
            raise ToolExecutionError(
                f"parent directory not found: {arguments.path}"
            ) from error
        except NotADirectoryError as error:
            raise ToolExecutionError(
                f"parent path is not a directory: {arguments.path}"
            ) from error
        except PermissionError as error:
            raise ToolExecutionError(f"permission denied: {arguments.path}") from error

        rendered_path = json.dumps(
            arguments.path,
            ensure_ascii=False,
        )
        return f"Created {rendered_path}."
