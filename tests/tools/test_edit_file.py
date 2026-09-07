from pathlib import Path

import pytest
from pydantic import ValidationError

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
from minicode.tools.edit_file import (
    EditFileArguments,
    EditFileTool,
)
from minicode.tools.registry import ToolRegistry
from minicode.tools.spec import ToolSpec
from minicode.workspace import Workspace


class FixedEditApprover:
    """Return one configured approval answer."""

    def __init__(
        self,
        *,
        approved: bool,
    ) -> None:
        self._approved = approved
        self.requests: list[tuple[ToolCall, str]] = []

    async def request_approval(
        self,
        tool_call: ToolCall,
        *,
        reason: str,
    ) -> bool:
        self.requests.append(
            (
                tool_call,
                reason,
            )
        )
        return self._approved


def test_edit_file_arguments_preserve_exact_replacement() -> None:
    arguments = EditFileArguments(
        path="README.md",
        old_text="M4 is next.",
        new_text="M5 is next.",
    )

    assert arguments.path == "README.md"
    assert arguments.old_text == "M4 is next."
    assert arguments.new_text == "M5 is next."


def test_edit_file_tool_exposes_spec(
    tmp_path: Path,
) -> None:
    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )

    assert tool.spec == ToolSpec(
        name="edit_file",
        description=("Replace one exact text occurrence inside a workspace file."),
        arguments_type=EditFileArguments,
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        "\t",
    ],
)
def test_edit_file_arguments_reject_blank_path(
    path: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="path must not be blank",
    ):
        EditFileArguments(
            path=path,
            old_text="before",
            new_text="after",
        )


def test_edit_file_arguments_reject_empty_old_text() -> None:
    with pytest.raises(
        ValidationError,
        match="old_text must not be empty",
    ):
        EditFileArguments(
            path="README.md",
            old_text="",
            new_text="replacement",
        )


def test_edit_file_arguments_allow_empty_new_text() -> None:
    arguments = EditFileArguments(
        path="README.md",
        old_text="remove this",
        new_text="",
    )

    assert arguments.new_text == ""


@pytest.mark.asyncio
async def test_edit_file_tool_replaces_one_exact_occurrence(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        ("first line\nbefore value\nlast line\n"),
        encoding="utf-8",
    )

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = EditFileArguments(
        path="example.txt",
        old_text="before value",
        new_text="after value",
    )

    output = await tool.execute(arguments)

    assert output == "Updated example.txt."
    assert source_file.read_text(
        encoding="utf-8",
    ) == ("first line\nafter value\nlast line\n")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "initial_content",
        "old_text",
        "expected_message",
    ),
    [
        (
            "existing text\n",
            "missing text",
            "old text not found: example.txt",
        ),
        (
            "repeat\nrepeat\n",
            "repeat",
            "old text is not unique: example.txt",
        ),
    ],
)
async def test_edit_file_tool_requires_one_exact_occurrence(
    tmp_path: Path,
    initial_content: str,
    old_text: str,
    expected_message: str,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        initial_content,
        encoding="utf-8",
    )

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = EditFileArguments(
        path="example.txt",
        old_text=old_text,
        new_text="replacement",
    )

    with pytest.raises(
        ToolExecutionError,
        match=expected_message,
    ):
        await tool.execute(arguments)

    assert (
        source_file.read_text(
            encoding="utf-8",
        )
        == initial_content
    )


@pytest.mark.asyncio
async def test_edit_file_tool_reports_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "secret value\n",
        encoding="utf-8",
    )

    tool = EditFileTool(
        workspace=Workspace(
            root=workspace_root,
        ),
    )
    arguments = EditFileArguments(
        path="../secret.txt",
        old_text="secret",
        new_text="exposed",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("cannot edit '../secret.txt': path is outside the workspace"),
    ) as exc_info:
        await tool.execute(arguments)

    assert isinstance(
        exc_info.value.__cause__,
        PermissionError,
    )
    assert (
        outside_file.read_text(
            encoding="utf-8",
        )
        == "secret value\n"
    )


@pytest.mark.asyncio
async def test_edit_file_tool_rejects_oversized_source(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        "123456",
        encoding="utf-8",
    )

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        max_bytes=5,
    )
    arguments = EditFileArguments(
        path="example.txt",
        old_text="1",
        new_text="x",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("file exceeds 5-byte edit limit: example.txt"),
    ):
        await tool.execute(arguments)

    assert (
        source_file.read_text(
            encoding="utf-8",
        )
        == "123456"
    )


@pytest.mark.asyncio
async def test_edit_file_tool_rejects_oversized_result(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        "a",
        encoding="utf-8",
    )

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
        max_bytes=5,
    )
    arguments = EditFileArguments(
        path="example.txt",
        old_text="a",
        new_text="123456",
    )

    with pytest.raises(
        ToolExecutionError,
        match=("updated file exceeds 5-byte edit limit: example.txt"),
    ):
        await tool.execute(arguments)

    assert (
        source_file.read_text(
            encoding="utf-8",
        )
        == "a"
    )


@pytest.mark.asyncio
async def test_edit_file_tool_reports_missing_file(
    tmp_path: Path,
) -> None:
    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = EditFileArguments(
        path="missing.txt",
        old_text="before",
        new_text="after",
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
async def test_edit_file_tool_rejects_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "docs"
    directory.mkdir()

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = EditFileArguments(
        path="docs",
        old_text="before",
        new_text="after",
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
async def test_edit_file_tool_rejects_non_utf8_file(
    tmp_path: Path,
) -> None:
    binary_file = tmp_path / "binary.dat"
    binary_file.write_bytes(b"\xff")

    tool = EditFileTool(
        workspace=Workspace(
            root=tmp_path,
        ),
    )
    arguments = EditFileArguments(
        path="binary.dat",
        old_text="before",
        new_text="after",
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
@pytest.mark.parametrize(
    (
        "approved",
        "expected_output",
        "expected_error",
        "expected_content",
    ),
    [
        (
            True,
            "Updated example.txt.",
            False,
            "after value\n",
        ),
        (
            False,
            "tool 'edit_file' approval denied",
            True,
            "before value\n",
        ),
    ],
)
async def test_edit_file_tool_respects_approval(
    tmp_path: Path,
    approved: bool,
    expected_output: str,
    expected_error: bool,
    expected_content: str,
) -> None:
    source_file = tmp_path / "example.txt"
    source_file.write_text(
        "before value\n",
        encoding="utf-8",
    )

    registry = ToolRegistry()
    registry.register(
        EditFileTool(
            workspace=Workspace(
                root=tmp_path,
            ),
        )
    )

    policy_reason = "editing files requires approval"
    policy = ConfiguredToolPolicy(
        decisions={
            "edit_file": PolicyDecision(
                outcome=PolicyOutcome.ASK,
                reason=policy_reason,
            ),
        },
    )
    approver = FixedEditApprover(
        approved=approved,
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        policy=policy,
        approver=approver,
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="edit_file",
        arguments={
            "path": "example.txt",
            "old_text": "before value",
            "new_text": "after value",
        },
    )

    result = await dispatcher.execute(tool_call)

    assert result == ToolResult(
        call_id="call_001",
        output=expected_output,
        is_error=expected_error,
    )
    assert (
        source_file.read_text(
            encoding="utf-8",
        )
        == expected_content
    )
    assert approver.requests == [
        (
            tool_call,
            policy_reason,
        )
    ]
