"""Hidden deterministic acceptance checks for the inventory contract case."""

import importlib.util
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import cast


def _load_module(
    workspace: Path,
    name: str,
) -> ModuleType:
    module_path = workspace / f"{name}.py"
    spec = importlib.util.spec_from_file_location(
        f"evaluated_{name}",
        module_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load evaluated {name}.py")

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
    """Verify the renamed contract and exact modification boundary."""
    inventory_module = _load_module(
        workspace,
        "inventory",
    )
    report_module = _load_module(
        workspace,
        "report",
    )
    inventory_record = cast(
        Callable[[str, int], dict[str, str | int]],
        inventory_module.inventory_record,
    )
    render_inventory = cast(
        Callable[[Mapping[str, str | int]], str],
        report_module.render_inventory,
    )

    record = inventory_record(
        "monitor",
        7,
    )

    assert record == {
        "name": "monitor",
        "stock": 7,
    }
    assert render_inventory(record) == "monitor: 7 units in stock"
    assert "quantity" not in (workspace / "inventory.py").read_text(encoding="utf-8")
    assert "quantity" not in (workspace / "report.py").read_text(encoding="utf-8")
    assert _changed_paths(workspace) == (
        "inventory.py",
        "report.py",
    )


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
    print("PASS multi_file_inventory_contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
