"""Independent pytest verifier for 02_circular_import."""

from __future__ import annotations

import importlib
import sys


def test_import_serializers_then_models() -> None:
    for mod in ("app.serializers", "app.models", "app"):
        sys.modules.pop(mod, None)
    serializers = importlib.import_module("app.serializers")
    models = importlib.import_module("app.models")
    user = models.User(user_id=7, name="Alice")
    assert serializers.serialize_user(user) == {"id": 7, "name": "Alice"}
    assert user.to_dict() == {"id": 7, "name": "Alice"}


def test_import_models_then_serializers() -> None:
    for mod in ("app.serializers", "app.models", "app"):
        sys.modules.pop(mod, None)
    models = importlib.import_module("app.models")
    serializers = importlib.import_module("app.serializers")
    user = models.User(user_id=9, name="Bob")
    assert user.to_dict() == {"id": 9, "name": "Bob"}
    assert serializers.serialize_user(user) == {"id": 9, "name": "Bob"}
