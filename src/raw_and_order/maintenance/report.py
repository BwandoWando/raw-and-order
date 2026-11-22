"""What a maintenance command reports when it finishes."""

from pathlib import Path

from pydantic import BaseModel, Field


class ProblemPhoto(BaseModel):
    """A stored photo the command could not handle, and why."""

    path: Path
    message: str


class MaintenanceSummary(BaseModel):
    """Counts shared by every maintenance command.

    Each stored photo ends up in exactly one of: ``updated``, ``unchanged``,
    ``failed``, or the command's own "missing" list.
    """

    checked: int = Field(default=0, description="Stored photos visited.")
    updated: int = Field(default=0, description="Photos whose stored data changed.")
    unchanged: int = Field(default=0, description="Photos already up to date.")
    failed: list[ProblemPhoto] = Field(default_factory=list)
