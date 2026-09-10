from pathlib import Path

import pytest

from minicode.tools.base import ToolExecutionError
from minicode.tools.list_files import (
    ListFilesArguments,
    ListFilesTool,
)
from minicode.workspace import (
    Workspace,
    WorkspaceFileLimitError,
    WorkspacePathError,
)


@pytest.mark.asyncio
async def test_list_files_tool_lists_nested_files_in_stable_order(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    nested_root = source_root / "nested"
    nested_root.mkdir(parents=True)
    (source_root / "b.py").write_text("", encoding="utf-8")
    (source_root / "a.py").write_text("", encoding="utf-8")
    (nested_root / "c.py").write_text("", encoding="utf-8")
    tool = ListFilesTool(
        workspace=Workspace(tmp_path),
    )

    output = await tool.execute(ListFilesArguments(path="src"))

    assert output == ('Files under "src":\nsrc/a.py\nsrc/b.py\nsrc/nested/c.py')


@pytest.mark.asyncio
async def test_list_files_tool_excludes_dependency_and_cache_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")

    for directory_name in (".git", ".venv", "node_modules"):
        ignored_root = tmp_path / directory_name
        ignored_root.mkdir()
        (ignored_root / "noise.py").write_text("", encoding="utf-8")

    tool = ListFilesTool(
        workspace=Workspace(tmp_path),
        max_files=1,
    )

    output = await tool.execute(ListFilesArguments())

    assert output == 'Files under ".":\nsrc/app.py'


@pytest.mark.asyncio
async def test_list_files_tool_reports_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    tool = ListFilesTool(
        workspace=Workspace(workspace_root),
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot list files outside the workspace"),
    ) as exc_info:
        await tool.execute(ListFilesArguments(path=".."))

    assert isinstance(
        exc_info.value.__cause__,
        WorkspacePathError,
    )


@pytest.mark.asyncio
async def test_list_files_tool_enforces_file_limit(
    tmp_path: Path,
) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("", encoding="utf-8")

    tool = ListFilesTool(
        workspace=Workspace(tmp_path),
        max_files=2,
    )

    with pytest.raises(
        ToolExecutionError,
        match="file listing exceeds 2-file limit",
    ) as exc_info:
        await tool.execute(ListFilesArguments())

    assert isinstance(
        exc_info.value.__cause__,
        WorkspaceFileLimitError,
    )
