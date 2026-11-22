"""CSS snippets shared by the UI's pages (pure strings, no Streamlit).

Streamlit gives every keyed element the class ``st-key-<key>``, which is how
these rules find their elements.
"""

FOCUS_RING = "#2a78d6"  # keyboard focus outline, visible on both themes


def keyed(key: str) -> str:
    """Selector of the element with Streamlit key ``key``."""
    return f".st-key-{key}"


def keyed_prefix(prefix: str) -> str:
    """Selector of every element whose Streamlit key starts with ``prefix``.

    It matches any class containing ``st-key-<prefix>``, so one prefix must
    never contain another that is used the same way.
    """
    return f'[class*="st-key-{prefix}"]'


def clickable_tile(tile: str, overlay: str) -> str:
    """Rules for a photo tile made clickable by a transparent button over it.

    The tile (selector ``tile``) holds an image and a real button (selector
    ``overlay``) stretched over it, so the click target is keyboard- and
    screen-reader-accessible while looking like the photo itself. The photo
    dims on hover and gets an outline when the button has keyboard focus.
    """
    return f"""
{tile} {{ position: relative; }}
{tile}:hover img {{ filter: brightness(0.85); }}
{overlay} {{
    position: absolute;
    inset: 0;
    z-index: 1;
}}
{overlay} * {{
    width: 100%;
    height: 100%;
}}
{overlay} button {{
    opacity: 0;
    cursor: pointer;
}}
{tile}:has(button:focus-visible) img {{
    outline: 3px solid {FOCUS_RING};
    outline-offset: 2px;
}}
"""


def visually_hidden(*selectors: str) -> str:
    """Hide elements on screen but keep them readable by screen readers."""
    return f"""
{", ".join(selectors)} {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
}}
"""


# Works around a Streamlit 1.67 multiselect bug. Its clear-all (x) and open
# (v) buttons are centred vertically. When the selected chips wrap onto a
# second line, pressing the mouse on x takes focus from the box, the box
# shrinks, the centred x moves up before the button is released, and no
# click happens: the selection stays. Pinned to the top (where a single line
# of chips puts them anyway), the buttons no longer move.
PINNED_MULTISELECT_BUTTONS = """
<style>
[data-testid="stMultiSelect"] [role="group"] > button {
    align-self: flex-start;
}
[data-testid="stMultiSelect"] [role="group"] > button[aria-label="Clear all"] {
    margin-top: 7px;
}
[data-testid="stMultiSelect"] [role="group"] > button[aria-label="Open"] {
    margin-top: 8px;
}
</style>
"""
