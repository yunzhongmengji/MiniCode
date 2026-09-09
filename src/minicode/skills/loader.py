"""Bounded loading of selected skill instructions."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.workspace import (
    Workspace,
    WorkspacePathError,
    WorkspaceReadLimitError,
)

_DEFAULT_MAX_BYTES = 50_000


class SkillLoadError(RuntimeError):
    """Raised when selected skill instructions cannot be loaded."""


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    """A manifest paired with its loaded instructions."""

    manifest: SkillManifest
    instructions: str


class SkillLoader(Protocol):
    """Load instructions for one selected skill."""

    async def load(
        self,
        manifest: SkillManifest,
    ) -> LoadedSkill:
        """Return the selected skill instructions."""
        ...


class FileSkillLoader:
    """Load instructions from an isolated skill directory."""

    def __init__(
        self,
        *,
        skill_root: Workspace,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if type(max_bytes) is not int:
            raise TypeError("max_bytes must be an integer")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        self._skill_root = skill_root
        self._max_bytes = max_bytes

    def _read_instructions(
        self,
        manifest: SkillManifest,
    ) -> str:
        """Read one skill within its own directory."""
        skill_directory = self._skill_root.resolve_path(manifest.name)
        skill_workspace = Workspace(
            root=skill_directory,
        )

        return skill_workspace.read_text(
            manifest.entrypoint,
            max_bytes=self._max_bytes,
        )

    async def load(
        self,
        manifest: SkillManifest,
    ) -> LoadedSkill:
        """Load one selected skill without blocking the event loop."""
        try:
            instructions = await asyncio.to_thread(
                self._read_instructions,
                manifest,
            )
        except WorkspacePathError as error:
            raise SkillLoadError(
                f"skill '{manifest.name}' entrypoint escapes its directory"
            ) from error
        except WorkspaceReadLimitError as error:
            raise SkillLoadError(
                f"skill '{manifest.name}' exceeds the {self._max_bytes}-byte limit"
            ) from error
        except (
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
            UnicodeDecodeError,
        ) as error:
            raise SkillLoadError(
                f"cannot load skill '{manifest.name}' instructions"
            ) from error

        if not instructions.strip():
            raise SkillLoadError(
                f"skill '{manifest.name}' instructions must not be blank"
            )

        return LoadedSkill(
            manifest=manifest,
            instructions=instructions,
        )
