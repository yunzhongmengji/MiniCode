"""Shared validation rules for tool arguments."""

from pydantic import BaseModel, ConfigDict


class ToolArguments(BaseModel):
    """Base model for validated arguments passed to tools."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )
