"""Discovery of skill manifests from a directory."""

import asyncio
import json
from pathlib import PurePosixPath

from minicode.skills.catalog import (
    SkillCatalog,
)
from minicode.skills.manifest import (
    SkillManifest,
)
from minicode.workspace import Workspace

_MANIFEST_FILENAME = "manifest.json"
_MAX_CATALOG_FILES = 1_000
_MAX_MANIFEST_BYTES = 10_000


class SkillCatalogLoadError(RuntimeError):
    """Raised when a skill manifest is invalid."""


def _is_manifest_path(
    path: str,
) -> bool:
    """Return whether a path is a top-level manifest."""
    parsed_path = PurePosixPath(path)

    return len(parsed_path.parts) == 2 and parsed_path.name == _MANIFEST_FILENAME


def _read_required_string(
    data: dict[str, object],
    *,
    field_name: str,
    manifest_path: str,
) -> str:
    """Read one required string from manifest data."""
    value = data.get(field_name)

    if not isinstance(value, str):
        raise SkillCatalogLoadError(
            f"skill manifest '{manifest_path}' field '{field_name}' must be a string"
        )

    return value


def _parse_manifest(
    *,
    manifest_path: str,
    content: str,
) -> SkillManifest:
    """Convert one JSON document into a manifest."""
    try:
        raw_data: object = json.loads(content)
    except json.JSONDecodeError as error:
        raise SkillCatalogLoadError(
            f"skill manifest '{manifest_path}' is not valid JSON"
        ) from error

    if not isinstance(raw_data, dict):
        raise SkillCatalogLoadError(
            f"skill manifest '{manifest_path}' must contain a JSON object"
        )

    data: dict[str, object] = {}

    for key, value in raw_data.items():
        if not isinstance(key, str):
            raise SkillCatalogLoadError(
                f"skill manifest '{manifest_path}' contains a non-string key"
            )

        data[key] = value

    raw_tags = data.get(
        "tags",
        [],
    )

    if not isinstance(raw_tags, list):
        raise SkillCatalogLoadError(
            f"skill manifest '{manifest_path}' field 'tags' must be a list"
        )

    tags: list[str] = []

    for tag in raw_tags:
        if not isinstance(tag, str):
            raise SkillCatalogLoadError(
                f"skill manifest '{manifest_path}' tags must contain strings"
            )

        tags.append(tag)

    try:
        return SkillManifest(
            name=_read_required_string(
                data,
                field_name="name",
                manifest_path=manifest_path,
            ),
            description=_read_required_string(
                data,
                field_name="description",
                manifest_path=manifest_path,
            ),
            entrypoint=_read_required_string(
                data,
                field_name="entrypoint",
                manifest_path=manifest_path,
            ),
            tags=tags,
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SkillCatalogLoadError(
            f"skill manifest '{manifest_path}' is invalid"
        ) from error


class FileSkillCatalogLoader:
    """Build a catalog from manifest files."""

    def __init__(
        self,
        *,
        skill_root: Workspace,
    ) -> None:
        self._skill_root = skill_root

    def _load_catalog(
        self,
    ) -> SkillCatalog:
        """Synchronously scan and build the catalog."""
        paths = self._skill_root.list_files(
            ".",
            max_files=_MAX_CATALOG_FILES,
        )
        manifest_paths = tuple(path for path in paths if _is_manifest_path(path))
        catalog = SkillCatalog()

        for manifest_path in manifest_paths:
            content = self._skill_root.read_text(
                manifest_path,
                max_bytes=(_MAX_MANIFEST_BYTES),
            )
            manifest = _parse_manifest(
                manifest_path=manifest_path,
                content=content,
            )
            directory_name = PurePosixPath(manifest_path).parts[0]

            if manifest.name != directory_name:
                raise SkillCatalogLoadError(
                    f"manifest name "
                    f"'{manifest.name}' "
                    "does not match directory "
                    f"'{directory_name}'"
                )

            catalog.register(manifest)

        return catalog

    async def load(
        self,
    ) -> SkillCatalog:
        """Build the catalog without blocking the event loop."""
        return await asyncio.to_thread(self._load_catalog)
