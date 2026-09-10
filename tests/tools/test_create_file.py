from pathlib import Path

import pytest

from minicode.tools.base import ToolExecutionError
from minicode.tools.create_file import (
    CreateFileArguments,
    CreateFileTool,
)
from minicode.workspace import Workspace, WorkspacePathError


@pytest.mark.asyncio
async def test_create_file_tool_creates_complete_utf8_file(
    tmp_path: Path,
) -> None:
    tool = CreateFileTool(
        workspace=Workspace(tmp_path),
    )

    output = await tool.execute(
        CreateFileArguments(
            path="example.py",
            content="value = '你好'\n",
        )
    )

    assert output == 'Created "example.py".'
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == ("value = '你好'\n")


@pytest.mark.asyncio
async def test_create_file_tool_does_not_overwrite_existing_file(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "example.py"
    target_path.write_text("original\n", encoding="utf-8")
    tool = CreateFileTool(
        workspace=Workspace(tmp_path),
    )

    with pytest.raises(
        ToolExecutionError,
        match="file already exists: example.py",
    ) as exc_info:
        await tool.execute(
            CreateFileArguments(
                path="example.py",
                content="replacement\n",
            )
        )

    assert isinstance(exc_info.value.__cause__, FileExistsError)
    assert target_path.read_text(encoding="utf-8") == "original\n"


@pytest.mark.asyncio
async def test_create_file_tool_rejects_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    tool = CreateFileTool(
        workspace=Workspace(workspace_root),
    )

    with pytest.raises(
        ToolExecutionError,
        match="cannot create '../outside.py': path is outside the workspace",
    ) as exc_info:
        await tool.execute(
            CreateFileArguments(
                path="../outside.py",
                content="secret\n",
            )
        )

    assert isinstance(exc_info.value.__cause__, WorkspacePathError)
    assert not (tmp_path / "outside.py").exists()


@pytest.mark.asyncio
async def test_create_file_tool_enforces_utf8_byte_limit(
    tmp_path: Path,
) -> None:
    tool = CreateFileTool(
        workspace=Workspace(tmp_path),
        max_bytes=2,
    )

    with pytest.raises(
        ToolExecutionError,
        match="new file exceeds 2-byte creation limit: example.txt",
    ):
        await tool.execute(
            CreateFileArguments(
                path="example.txt",
                content="你",
            )
        )

    assert not (tmp_path / "example.txt").exists()
