"""Catalog used to discover skills by name."""

from minicode.skills.manifest import (
    SkillManifest,
)


class SkillCatalog:
    """Store lightweight skill manifests."""

    def __init__(self) -> None:
        self._manifests: dict[
            str,
            SkillManifest,
        ] = {}

    @property
    def manifests(
        self,
    ) -> tuple[SkillManifest, ...]:
        """Return manifests in registration order."""
        return tuple(self._manifests.values())

    def register(
        self,
        manifest: SkillManifest,
    ) -> None:
        """Register one manifest by its name."""
        name = manifest.name

        if name in self._manifests:
            raise ValueError(f"skill '{name}' is already registered")

        self._manifests[name] = manifest

    def get(
        self,
        name: str,
    ) -> SkillManifest | None:
        """Return a manifest, or None if unknown."""
        return self._manifests.get(name)
