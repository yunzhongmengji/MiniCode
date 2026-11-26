"""Domain models."""

from dataclasses import dataclass

from app.serializers import serialize_user  # BUG: circular top-level import


@dataclass(frozen=True)
class User:
    user_id: int
    name: str

    def to_dict(self) -> dict[str, object]:
        return serialize_user(self)
