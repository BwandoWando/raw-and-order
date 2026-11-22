"""StateUpdate must mirror WorkflowState, or typed step results would lie."""

from typing import get_type_hints

from raw_and_order.workflow.state import StateUpdate, WorkflowState

RUN_SETTINGS = {
    "source_dir",
    "reprocess",
    "reprocess_failed",
    "max_photos",
    "chunk_size",
}


def test_every_changeable_state_field_is_in_state_update() -> None:
    assert (
        set(get_type_hints(StateUpdate))
        == set(WorkflowState.model_fields) - RUN_SETTINGS
    )


def test_state_update_fields_have_the_state_field_types() -> None:
    for name, expected in get_type_hints(StateUpdate).items():
        assert WorkflowState.model_fields[name].annotation == expected, name
