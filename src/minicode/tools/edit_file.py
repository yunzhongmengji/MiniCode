"""Tool for exact text replacement inside workspace files."""

import asyncio

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import (
    Workspace,
    WorkspacePathError,
    WorkspaceReadLimitError,
)


class EditFileArguments(ToolArguments):
    """Validated arguments accepted by exact file editing."""

    path: str = Field(
        description=("Path to the UTF-8 text file, relative to the workspace root."),
    )
    old_text: str = Field(
        description=("Exact existing text to replace."),
    )
    new_text: str = Field(
        description=("Replacement text. May be empty to delete old_text."),
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

    @field_validator("old_text")
    @classmethod
    def validate_old_text_not_empty(
        cls,
        value: str,
    ) -> str:
        """Reject an empty replacement target."""
        if value == "":
            raise ValueError("old_text must not be empty")

        return value


_DEFAULT_MAX_BYTES = 100_000


_EDIT_FILE_SPEC = ToolSpec(
    name="edit_file",
    description=("Replace one exact text occurrence inside a workspace file."),
    arguments_type=EditFileArguments,
)


class EditFileTool:
    """Replace one exact text occurrence in a workspace file."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if isinstance(
            max_bytes,
            bool,
        ) or not isinstance(
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
        return _EDIT_FILE_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Replace one exact occurrence in an existing file."""
        if not isinstance(
            arguments,
            EditFileArguments,
        ):
            raise TypeError("arguments must be EditFileArguments")

        try:
            content = await asyncio.to_thread(
                self._workspace.read_text,
                arguments.path,
                max_bytes=self._max_bytes,
            )

            occurrence_count = content.count(arguments.old_text)

            if occurrence_count == 0:
                raise ToolExecutionError(f"old text not found: {arguments.path}")

            if occurrence_count > 1:
                raise ToolExecutionError(f"old text is not unique: {arguments.path}")

            updated_content = content.replace(
                arguments.old_text,
                arguments.new_text,
                1,
            )

            updated_size = len(updated_content.encode("utf-8"))

            if updated_size > self._max_bytes:
                raise ToolExecutionError(
                    f"updated file exceeds "
                    f"{self._max_bytes}-byte "
                    f"edit limit: "
                    f"{arguments.path}"
                )

            await asyncio.to_thread(
                self._workspace.write_text,
                arguments.path,
                updated_content,
            )

        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot edit '{arguments.path}': path is outside the workspace"
            ) from error
        except WorkspaceReadLimitError as error:
            raise ToolExecutionError(
                f"file exceeds {self._max_bytes}-byte edit limit: {arguments.path}"
            ) from error
        except FileNotFoundError as error:
            raise ToolExecutionError(f"file not found: {arguments.path}") from error
        except IsADirectoryError as error:
            raise ToolExecutionError(f"path is not a file: {arguments.path}") from error
        except UnicodeDecodeError as error:
            raise ToolExecutionError(
                f"file is not valid UTF-8: {arguments.path}"
            ) from error

        return f"Updated {arguments.path}."
