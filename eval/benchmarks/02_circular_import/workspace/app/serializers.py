"""Model serializers."""

from app.models import User


def serialize_user(user: User) -> dict[str, object]:
    """Serialize a User dataclass into a plain dictionary."""
    return {"id": user.user_id, "name": user.name}
