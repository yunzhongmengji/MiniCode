from pathlib import Path

import pytest
from pydantic import ValidationError

from minicode.tools.base import ToolExecutionError
from minicode.tools.read_file import (
    ReadFileArguments,
    ReadFileTool,
)
from minicode.workspace import Workspace


@pytest.mark.asyncio
async def test_read_file_tool_reads_workspace_file(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text(
        "MiniCode 工作区",
        encoding="utf-8",
    )
    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "README.md",
        }
    )

    output = await tool.execute(arguments)

    assert output == "MiniCode 工作区"


@pytest.mark.asyncio
async def test_read_file_tool_reports_missing_file(
    tmp_path: Path,
) -> None:
    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "missing.txt",
        }
    )

    with pytest.raises(
        ToolExecutionError,
        match="file not found: missing.txt",
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        FileNotFoundError,
    )


@pytest.mark.asyncio
async def test_read_file_tool_reports_workspace_escape(
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
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "../secret.txt",
        }
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot read '../secret.txt': path is outside the workspace"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )


@pytest.mark.asyncio
async def test_read_file_tool_rejects_directory(
    tmp_path: Path,
) -> None:
    directory_path = tmp_path / "docs"
    directory_path.mkdir()

    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "docs",
        }
    )

    with pytest.raises(
        ToolExecutionError,
        match="path is not a file: docs",
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        IsADirectoryError,
    )


@pytest.mark.asyncio
async def test_read_file_tool_rejects_non_utf8_file(
    tmp_path: Path,
) -> None:
    binary_file = tmp_path / "binary.dat"
    binary_file.write_bytes(b"\xff")

    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "binary.dat",
        }
    )

    with pytest.raises(
        ToolExecutionError,
        match="file is not valid UTF-8: binary.dat",
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        UnicodeDecodeError,
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        "\t",
    ],
)
def test_read_file_arguments_reject_blank_path(
    path: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="path must not be blank",
    ):
        ReadFileArguments.model_validate(
            {
                "path": path,
            }
        )


def test_read_file_tool_exposes_model_facing_spec(
    tmp_path: Path,
) -> None:
    tool = ReadFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )

    spec = tool.spec
    parameters_schema = spec.arguments_type.model_json_schema()

    assert spec.name == "read_file"
    assert spec.description == ("Read a UTF-8 text file from the workspace.")
    assert spec.arguments_type is ReadFileArguments
    assert parameters_schema["required"] == ["path"]
    assert parameters_schema["properties"]["path"]["description"] == (
        "Path to a UTF-8 text file, relative to the workspace root."
    )


@pytest.mark.asyncio
async def test_read_file_tool_reports_permission_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "README.md",
        }
    )

    def deny_read_text(
        _relative_path: str,
        *,
        max_bytes: int | None = None,
    ) -> str:
        raise PermissionError("operating system denied access")

    monkeypatch.setattr(
        workspace,
        "read_text",
        deny_read_text,
    )

    with pytest.raises(
        ToolExecutionError,
        match="permission denied: README.md",
    ) as exc_info:
        await tool.execute(arguments)

    assert type(exc_info.value.__cause__) is PermissionError


@pytest.mark.asyncio
async def test_read_file_tool_rejects_file_over_byte_limit(
    tmp_path: Path,
) -> None:
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"123456")

    workspace = Workspace(
        root=tmp_path,
    )
    tool = ReadFileTool(
        workspace=workspace,
        max_bytes=5,
    )
    arguments = ReadFileArguments.model_validate(
        {
            "path": "large.txt",
        }
    )

    with pytest.raises(
        ToolExecutionError,
        match=("file exceeds 5-byte read limit: large.txt"),
    ):
        await tool.execute(arguments)


@pytest.mark.parametrize(
    "max_bytes",
    [
        True,
        1.5,
        "5",
        None,
    ],
)
def test_read_file_tool_rejects_non_integer_byte_limit(
    tmp_path: Path,
    max_bytes: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="max_bytes must be an integer",
    ):
        ReadFileTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            max_bytes=max_bytes,
        )


@pytest.mark.parametrize(
    "max_bytes",
    [
        0,
        -1,
    ],
)
def test_read_file_tool_rejects_non_positive_byte_limit(
    tmp_path: Path,
    max_bytes: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_bytes must be greater than zero",
    ):
        ReadFileTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            max_bytes=max_bytes,
        )
