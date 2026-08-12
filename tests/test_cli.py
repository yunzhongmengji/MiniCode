import pytest

from minicode.cli import main


def test_dry_run_reports_task_without_execution(capsys) -> None:
    exit_code = main(["run", "修复测试", "--dry-run"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Task: 修复测试" in captured.out
    assert "Dry run: no files were changed." in captured.out


def test_run_without_dry_run_reports_not_implemented(capsys) -> None:
    exit_code = main(["run", "修复测试"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Task execution is not implemented yet." in captured.err


def test_missing_command_exits_with_usage_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "the following arguments are required" in captured.err
