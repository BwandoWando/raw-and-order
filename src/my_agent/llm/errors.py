"""Provider exception types, resolved lazily from installed packages.

Lets the annotator catch specific provider errors without importing SDKs
for providers that are not installed.
"""

import importlib
from functools import cache

_TRANSIENT = {
    "httpx": ("TransportError",),
    "openai": (
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
    ),
    "anthropic": (
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
    ),
}

_PROVIDER = {
    "httpx": ("HTTPError",),
    "ollama": ("ResponseError", "RequestError"),
    "openai": ("APIError",),
    "anthropic": ("APIError",),
}


@cache
def transient_errors() -> tuple[type[Exception], ...]:
    """Errors worth retrying: timeouts, dropped connections, rate limits."""
    return _resolve(_TRANSIENT)


@cache
def provider_errors() -> tuple[type[Exception], ...]:
    """All provider/client errors, retryable or not."""
    return _resolve(_PROVIDER)


def _resolve(spec: dict[str, tuple[str, ...]]) -> tuple[type[Exception], ...]:
    found: list[type[Exception]] = []
    for module_name, names in spec.items():
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        found.extend(getattr(module, name) for name in names if hasattr(module, name))
    return tuple(found)
