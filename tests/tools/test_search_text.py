from pathlib import Path

import pytest

from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.core.tool_policy import (
    ConfiguredToolPolicy,
    PolicyDecision,
    PolicyOutcome,
)
from minicode.tools.base import ToolExecutionError
from minicode.tools.dispatcher import ToolDispatcher
from minicode.tools.registry import ToolRegistry
from minicode.tools.search_text import (
    SearchTextArguments,
    SearchTextTool,
)
from minicode.tools.spec import ToolSpec
from minicode.workspace import Workspace


def test_search_text_tool_exposes_spec(
    tmp_path: Path,
) -> None:
    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )

    assert tool.spec == ToolSpec(
        name="search_text",
        description=(
            "Search for literal text inside UTF-8 workspace files. Directory "
            "searches skip non-UTF-8 and oversized files."
        ),
        arguments_type=SearchTextArguments,
    )


def test_search_text_arguments_preserve_query_and_default_path() -> None:
    arguments = SearchTextArguments(
        query="PolicyOutcome",
    )

    assert arguments.query == "PolicyOutcome"
    assert arguments.path == "."


def test_search_text_arguments_preserve_explicit_path() -> None:
    arguments = SearchTextArguments(
        query="PolicyOutcome",
        path="src/minicode",
    )

    assert arguments.query == "PolicyOutcome"
    assert arguments.path == "src/minicode"


@pytest.mark.parametrize(
    (
        "field_name",
        "field_value",
    ),
    [
        (
            "query",
            "",
        ),
        (
            "query",
            " ",
        ),
        (
            "path",
            "",
        ),
        (
            "path",
            "\t",
        ),
    ],
)
def test_search_text_arguments_reject_blank_strings(
    field_name: str,
    field_value: str,
) -> None:
    values = {
        "query": "PolicyOutcome",
        "path": ".",
    }
    values[field_name] = field_value

    with pytest.raises(
        ValueError,
        match=(f"{field_name} must not be blank"),
    ):
        SearchTextArguments.model_validate(values)


@pytest.mark.asyncio
async def test_search_text_tool_finds_literal_matches_in_file(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "src" / "example.txt"
    source_path.parent.mkdir()
    source_path.write_text(
        ("axb\na.b\nprefix a.b suffix\n"),
        encoding="utf-8",
    )
    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = SearchTextArguments(
        query="a.b",
        path="src/example.txt",
    )

    output = await tool.execute(arguments)

    assert output == ("src/example.txt:2:a.b\nsrc/example.txt:3:prefix a.b suffix")


@pytest.mark.asyncio
async def test_search_text_tool_reports_no_matches(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "example.txt"
    source_path.write_text(
        "MiniCode workspace\n",
        encoding="utf-8",
    )
    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = SearchTextArguments(
        query="PolicyOutcome",
        path="example.txt",
    )

    output = await tool.execute(arguments)

    assert output == "No matches found."


@pytest.mark.asyncio
async def test_search_text_tool_limits_matches(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "example.txt"
    source_path.write_text(
        ("match one\nmatch two\nmatch three\n"),
        encoding="utf-8",
    )
    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        max_results=2,
    )
    arguments = SearchTextArguments(
        query="match",
        path="example.txt",
    )

    output = await tool.execute(arguments)

    assert output == ("example.txt:1:match one\nexample.txt:2:match two")


@pytest.mark.parametrize(
    "max_results",
    [
        True,
        1.5,
        "2",
    ],
)
def test_search_text_tool_rejects_non_integer_result_limit(
    tmp_path: Path,
    max_results: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="max_results must be an integer",
    ):
        SearchTextTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            max_results=max_results,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "max_results",
    [
        0,
        -1,
    ],
)
def test_search_text_tool_rejects_non_positive_result_limit(
    tmp_path: Path,
    max_results: int,
) -> None:
    with pytest.raises(
        ValueError,
        match=("max_results must be greater than zero"),
    ):
        SearchTextTool(
            workspace=Workspace(
                root=tmp_path,
            ),
            max_results=max_results,
        )


@pytest.mark.asyncio
async def test_search_text_tool_searches_directory_in_stable_order(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    nested_root = source_root / "nested"
    nested_root.mkdir(
        parents=True,
    )

    (source_root / "b.txt").write_text(
        "needle from b\n",
        encoding="utf-8",
    )
    (source_root / "a.txt").write_text(
        ("first line\nneedle from a\n"),
        encoding="utf-8",
    )
    (nested_root / "c.txt").write_text(
        "needle from c\n",
        encoding="utf-8",
    )
    (nested_root / "ignored.txt").write_text(
        "nothing here\n",
        encoding="utf-8",
    )

    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = SearchTextArguments(
        query="needle",
        path="src",
    )

    output = await tool.execute(arguments)

    assert output == (
        "src/a.txt:2:needle from a\n"
        "src/b.txt:1:needle from b\n"
        "src/nested/c.txt:1:needle from c"
    )


@pytest.mark.asyncio
async def test_search_text_tool_excludes_dependency_directories_before_limit(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text(
        "project needle\n",
        encoding="utf-8",
    )
    dependency_root = tmp_path / ".venv"
    dependency_root.mkdir()
    (dependency_root / "package.py").write_text(
        "dependency needle\n",
        encoding="utf-8",
    )
    tool = SearchTextTool(
        workspace=Workspace(tmp_path),
        max_files=1,
    )

    output = await tool.execute(SearchTextArguments(query="needle"))

    assert output == "app.py:1:project needle"


@pytest.mark.asyncio
async def test_search_text_tool_skips_unreadable_files_in_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text(
        "project needle\n",
        encoding="utf-8",
    )
    (tmp_path / "image.bin").write_bytes(b"\xff")
    (tmp_path / "large.txt").write_text(
        "x" * 100_001,
        encoding="utf-8",
    )
    tool = SearchTextTool(
        workspace=Workspace(tmp_path),
    )

    output = await tool.execute(SearchTextArguments(query="needle"))

    assert output == "app.py:1:project needle"


@pytest.mark.asyncio
async def test_search_text_tool_rejects_directory_over_file_limit(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()

    for index in range(3):
        (source_root / f"{index}.txt").write_text(
            "no matches\n",
            encoding="utf-8",
        )

    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        max_files=2,
    )
    arguments = SearchTextArguments(
        query="needle",
        path="src",
    )

    with pytest.raises(
        ToolExecutionError,
        match="search exceeds 2-file limit: src",
    ):
        await tool.execute(arguments)


@pytest.mark.asyncio
async def test_search_text_tool_reports_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret value\n",
        encoding="utf-8",
    )

    tool = SearchTextTool(
        workspace=Workspace(
            root=workspace_root,
        ),
    )
    arguments = SearchTextArguments(
        query="secret",
        path="../secret.txt",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot search '../secret.txt': path is outside the workspace"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )


@pytest.mark.asyncio
async def test_search_text_tool_reports_nested_symlink_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret value\n",
        encoding="utf-8",
    )

    linked_file = workspace_root / "linked-secret.txt"
    linked_file.symlink_to(outside_file)

    tool = SearchTextTool(
        workspace=Workspace(
            root=workspace_root,
        ),
    )
    arguments = SearchTextArguments(
        query="secret",
        path=".",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot search '.': path is outside the workspace"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )


@pytest.mark.asyncio
async def test_search_text_tool_reports_missing_path(
    tmp_path: Path,
) -> None:
    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = SearchTextArguments(
        query="needle",
        path="missing.txt",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("search path not found: missing.txt"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        FileNotFoundError,
    )


@pytest.mark.asyncio
async def test_search_text_tool_rejects_non_utf8_file(
    tmp_path: Path,
) -> None:
    binary_file = tmp_path / "binary.dat"
    binary_file.write_bytes(b"\xff")

    tool = SearchTextTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = SearchTextArguments(
        query="needle",
        path="binary.dat",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("file is not valid UTF-8: binary.dat"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        UnicodeDecodeError,
    )


@pytest.mark.asyncio
async def test_search_text_tool_runs_through_dispatcher(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        ("first line\nfind this line\n"),
        encoding="utf-8",
    )

    registry = ToolRegistry()
    registry.register(
        SearchTextTool(
            workspace=Workspace(
                root=tmp_path,
            ),
        )
    )

    policy = ConfiguredToolPolicy(
        decisions={
            "search_text": PolicyDecision(
                outcome=PolicyOutcome.ALLOW,
                reason=("search is allowed during this test"),
            ),
        },
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="search_text",
        arguments={
            "query": "find",
            "path": "example.txt",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output=("example.txt:2:find this line"),
        is_error=False,
    )
