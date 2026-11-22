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


# HTTP statuses that mean "the model/provider is unusable", not "this image".
UNAVAILABLE_STATUSES = frozenset({401, 403, 404, 408, 429})
SERVER_ERROR_MIN = 500
CLIENT_ERROR_MIN = 400


def status_code(exc: BaseException) -> int | None:
    """Return the HTTP status attached to a provider/client error, if any."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def is_unavailable(exc: BaseException) -> bool:
    """True if ``exc`` means the LLM cannot be used at all (stop the run).

    No status (connection refused, DNS, timeout), auth errors, model not
    found, rate limits and server errors (after retries) are outages. Other
    4xx are about the request itself, i.e. this image.
    """
    status = status_code(exc)
    if status is None:
        return True
    if status in UNAVAILABLE_STATUSES or status >= SERVER_ERROR_MIN:
        return True
    return status < CLIENT_ERROR_MIN  # odd 1xx/2xx/3xx: treat as outage
