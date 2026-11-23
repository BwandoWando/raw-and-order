import pytest
from pydantic import ValidationError

from raw_and_order.schemas import Annotation, SceneType


def test_description_and_tags_are_stripped_of_stray_whitespace() -> None:
    annotation = Annotation(
        description="  A ferris wheel at 17:04. ",
        tags=[" ferris wheel ", "sky\n"],
        scene=SceneType.ARCHITECTURE,
        contains_people=False,
    )

    assert annotation.description == "A ferris wheel at 17:04."
    assert annotation.tags == ["ferris wheel", "sky"]


def test_a_description_of_only_whitespace_is_invalid() -> None:
    with pytest.raises(ValidationError):
        Annotation(description="   ", scene=SceneType.OTHER, contains_people=False)
