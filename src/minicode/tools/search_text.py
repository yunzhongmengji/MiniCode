"""Tool for literal text search inside a workspace."""

import asyncio

from pydantic import Field, field_validator

from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec
from minicode.workspace import (
    Workspace,
    WorkspaceFileLimitError,
    WorkspacePathError,
)

_DEFAULT_MAX_BYTES = 100_000
_DEFAULT_MAX_RESULTS = 100
_DEFAULT_MAX_FILES = 1_000


class SearchTextArguments(ToolArguments):
    """Validated arguments accepted by text search."""

    query: str = Field(
        description=("Literal text to search for."),
    )
    path: str = Field(
        default=".",
        description=("File or directory to search, relative to the workspace root."),
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject blank search text."""
        if not value.strip():
            raise ValueError("query must not be blank")

        return value

    @field_validator("path")
    @classmethod
    def validate_path_not_blank(
        cls,
        value: str,
    ) -> str:
        """Reject blank search paths."""
        if not value.strip():
            raise ValueError("path must not be blank")

        return value


_SEARCH_TEXT_SPEC = ToolSpec(
    name="search_text",
    description=("Search for literal text inside workspace files."),
    arguments_type=SearchTextArguments,
)


class SearchTextTool:
    """Search workspace files for literal text."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_results: int = _DEFAULT_MAX_RESULTS,
        max_files: int = _DEFAULT_MAX_FILES,
    ) -> None:
        if isinstance(
            max_results,
            bool,
        ) or not isinstance(
            max_results,
            int,
        ):
            raise TypeError("max_results must be an integer")

        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

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

        self._workspace = workspace
        self._max_results = max_results
        self._max_files = max_files

    @property
    def spec(self) -> ToolSpec:
        """Return immutable metadata describing this tool."""
        return _SEARCH_TEXT_SPEC

    async def execute(
        self,
        arguments: ToolArguments,
    ) -> str:
        """Search workspace files for literal text."""
        if not isinstance(
            arguments,
            SearchTextArguments,
        ):
            raise TypeError("arguments must be SearchTextArguments")

        try:
            paths = await asyncio.to_thread(
                self._workspace.list_files,
                arguments.path,
                max_files=self._max_files,
            )

            matches: list[str] = []

            for path in paths:
                content = await asyncio.to_thread(
                    self._workspace.read_text,
                    path,
                    max_bytes=_DEFAULT_MAX_BYTES,
                )

                for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
                ):
                    if arguments.query not in line:
                        continue

                    matches.append(f"{path}:{line_number}:{line}")

                    if len(matches) >= self._max_results:
                        return "\n".join(matches)

            if not matches:
                return "No matches found."

            return "\n".join(matches)

        except WorkspacePathError as error:
            raise ToolExecutionError(
                f"cannot search '{arguments.path}': path is outside the workspace"
            ) from error
        except WorkspaceFileLimitError as error:
            raise ToolExecutionError(
                f"search exceeds {self._max_files}-file limit: {arguments.path}"
            ) from error
        except FileNotFoundError as error:
            raise ToolExecutionError(
                f"search path not found: {arguments.path}"
            ) from error
        except UnicodeDecodeError as error:
            raise ToolExecutionError(
                f"file is not valid UTF-8: {arguments.path}"
            ) from error
