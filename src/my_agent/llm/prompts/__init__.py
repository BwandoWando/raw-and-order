"""Prompt templates stored as text files in this package."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return the text of ``<name>.md`` from this package."""
    return (files(__package__) / f"{name}.md").read_text(encoding="utf-8")
