"""Hidden deterministic acceptance checks for single_file_batching."""

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast


def _load_module(workspace: Path) -> ModuleType:
    module_path = workspace / "batching.py"
    spec = importlib.util.spec_from_file_location(
        "evaluated_batching",
        module_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("could not load evaluated batching.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _changed_paths(workspace: Path) -> tuple[str, ...]:
    result = subprocess.run(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
        ),
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line[3:] for line in result.stdout.splitlines() if line)


def verify(workspace: Path) -> None:
    """Verify behavior and the allowed modification boundary."""
    module = _load_module(workspace)
    batches = cast(
        Callable[[list[object], int], list[list[object]]],
        module.batches,
    )

    values: list[object] = [
        "a",
        "b",
        "c",
        "d",
        "e",
    ]
    original = list(values)

    assert batches(values, 2) == [
        ["a", "b"],
        ["c", "d"],
        ["e"],
    ]
    assert batches(values, 1) == [
        ["a"],
        ["b"],
        ["c"],
        ["d"],
        ["e"],
    ]
    assert batches([], 3) == []
    assert values == original
    assert _changed_paths(workspace) == ("batching.py",)


def main() -> int:
    """Run the acceptance check for one prepared workspace."""
    if len(sys.argv) != 2:
        print(
            "usage: acceptance.py WORKSPACE",
            file=sys.stderr,
        )
        return 2

    workspace = Path(sys.argv[1]).resolve(
        strict=True,
    )
    verify(workspace)
    print("PASS single_file_batching")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
