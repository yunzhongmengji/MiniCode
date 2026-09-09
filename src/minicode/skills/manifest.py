"""Metadata describing lazily loaded skills."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """Describe one skill without loading its instructions."""

    name: str
    description: str
    entrypoint: str
    tags: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Validate and snapshot skill metadata."""
        text_fields = (
            (
                "name",
                self.name,
            ),
            (
                "description",
                self.description,
            ),
            (
                "entrypoint",
                self.entrypoint,
            ),
        )

        for field_name, value in text_fields:
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if not isinstance(
            self.tags,
            Sequence,
        ) or isinstance(
            self.tags,
            (str, bytes),
        ):
            raise TypeError("tags must be a sequence")

        normalized_tags = tuple(self.tags)

        for tag in normalized_tags:
            if not isinstance(tag, str):
                raise TypeError("tags must contain only strings")

            if not tag.strip():
                raise ValueError("tags must not contain blank strings")

        if len(set(normalized_tags)) != len(normalized_tags):
            raise ValueError("tags must be unique")

        object.__setattr__(
            self,
            "tags",
            normalized_tags,
        )
