"""Prompt templates stored as text files in this package."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return the text of ``<name>.md`` from this package."""
    return (files(__package__) / f"{name}.md").read_text(encoding="utf-8")


def render_prompt(name: str, **values: object) -> str:
    """Load ``<name>.md`` and fill ``{placeholder}`` markers with ``values``.

    Only the given placeholders are replaced, so other braces in the text are
    left alone.

    Raises:
        KeyError: If a given placeholder does not occur in the prompt.
    """
    text = load_prompt(name)
    for key, value in values.items():
        marker = "{" + key + "}"
        if marker not in text:
            raise KeyError(f"Prompt {name!r} has no {marker} placeholder")
        text = text.replace(marker, str(value))
    return text
