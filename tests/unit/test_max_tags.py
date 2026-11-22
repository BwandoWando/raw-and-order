import pytest
from pydantic import SecretStr, ValidationError

from raw_and_order.bootstrap import build_annotator
from raw_and_order.config import LLMSettings, Settings
from raw_and_order.exceptions import ConfigurationError
from raw_and_order.llm.annotator import LLMAnnotator
from raw_and_order.llm.prompts import render_prompt
from raw_and_order.schemas import Annotation, SceneType
from raw_and_order.schemas.annotation import MAX_TAGS_LIMIT, annotation_schema
from tests.fakes import ScriptedChatModel


def _fields(tags: int) -> dict[str, object]:
    return {
        "description": "x",
        "tags": [f"t{i}" for i in range(tags)],
        "scene": SceneType.OTHER,
        "contains_people": False,
    }


def test_limited_schema_enforces_its_own_limit() -> None:
    schema = annotation_schema(5)

    schema.model_validate(_fields(5))
    with pytest.raises(ValidationError, match="at most 5"):
        schema.model_validate(_fields(6))


def test_limit_is_in_the_json_schema_the_model_sees() -> None:
    json_schema = annotation_schema(7).model_json_schema()

    assert json_schema["title"] == "Annotation"
    assert json_schema["properties"]["tags"]["maxItems"] == 7


def test_limited_schema_is_built_once_per_limit() -> None:
    assert annotation_schema(9) is annotation_schema(9)
    assert annotation_schema(9) is not annotation_schema(10)


def test_stored_annotations_allow_up_to_the_hard_limit() -> None:
    Annotation.model_validate(_fields(MAX_TAGS_LIMIT))
    with pytest.raises(ValidationError):
        Annotation.model_validate(_fields(MAX_TAGS_LIMIT + 1))


def test_prompt_placeholder_is_filled() -> None:
    prompt = render_prompt("annotate_system", max_tags=7)

    assert "up to 7 short lowercase keywords" in prompt
    assert "{max_tags}" not in prompt


def test_unknown_placeholder_is_an_error() -> None:
    with pytest.raises(ConfigurationError, match="no_such_value"):
        render_prompt("annotate_system", no_such_value=1)


def test_annotator_returns_plain_annotation() -> None:
    limited = annotation_schema(3).model_validate(_fields(3))
    annotator = LLMAnnotator(
        ScriptedChatModel(script=[limited]),
        "system",
        output_schema=annotation_schema(3),
        max_retries=1,
    )

    result = annotator.annotate(b"jpeg", None)

    assert type(result) is Annotation
    assert result.tags == ["t0", "t1", "t2"]


def test_max_tags_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).max_tags == 20
    monkeypatch.setenv("MAX_TAGS", "30")
    assert Settings(_env_file=None).max_tags == 30


@pytest.mark.parametrize("value", ["0", str(MAX_TAGS_LIMIT + 1)])
def test_max_tags_outside_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_TAGS", value)

    with pytest.raises(ValidationError, match="max_tags"):
        Settings(_env_file=None)


def test_bootstrap_uses_one_value_for_prompt_and_schema() -> None:
    llm = LLMSettings(model="gemma3:12b", api_key=SecretStr("unused"))

    annotator = build_annotator(llm, max_tags=12)

    assert "up to 12 short lowercase keywords" in annotator._system_prompt
