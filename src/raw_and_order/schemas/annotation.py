"""Annotation produced by the LLM.

Kept deliberately flat with enums where possible so that smaller local
models can produce valid structured output reliably.
"""

from enum import StrEnum
from functools import cache

from pydantic import BaseModel, ConfigDict, Field, create_model

DEFAULT_MAX_TAGS = 20
MAX_TAGS_LIMIT = 50  # upper bound for MAX_TAGS; stored annotations never exceed it
TAGS_DESCRIPTION = "Short lowercase keywords, e.g. 'sunset', 'mountain'."


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
    """Structured description of a photo.

    Leading and trailing whitespace is stripped from the description and each
    tag, both from the model's answer and from stored rows read back: models
    sometimes end a description with a space, which breaks Markdown bold.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    description: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Two or three sentences describing the photo, the scene, "
            "and the subject(s)."
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=MAX_TAGS_LIMIT,
        description=TAGS_DESCRIPTION,
    )
    scene: SceneType = Field(description="The best matching scene category.")
    contains_people: bool = Field(description="True if any person is visible.")


@cache
def annotation_schema(max_tags: int) -> type[Annotation]:
    """Return an :class:`Annotation` variant that allows at most ``max_tags`` tags.

    This is the schema the LLM is asked to fill (and validated against), so the
    limit comes from the ``MAX_TAGS`` setting. Results are converted back to
    plain :class:`Annotation` before they are stored.
    """
    limited: type[Annotation] = create_model(
        "Annotation",
        __base__=Annotation,
        tags=(
            list[str],
            Field(
                default_factory=list, max_length=max_tags, description=TAGS_DESCRIPTION
            ),
        ),
    )
    return limited
