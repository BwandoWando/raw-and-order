"""Annotation produced by the LLM.

Kept deliberately flat with enums where possible so that smaller local
models can produce valid structured output reliably.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SceneType(StrEnum):
    """High-level category of the photo."""

    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    STREET = "street"
    WILDLIFE = "wildlife"
    ARCHITECTURE = "architecture"
    MACRO = "macro"
    EVENT = "event"
    FOOD = "food"
    OTHER = "other"


class Annotation(BaseModel):
    """Structured description of a photo."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(
        min_length=1,
        max_length=500,
        description="One or two sentences describing the photo.",
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="Short lowercase keywords, e.g. 'sunset', 'mountain'.",
    )
    scene: SceneType = Field(description="The best matching scene category.")
    contains_people: bool = Field(description="True if any person is visible.")
