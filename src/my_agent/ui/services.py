"""Cached access to the read-only services, for every UI module."""

from pathlib import Path

import streamlit as st

from my_agent.bootstrap import UiServices, build_ui_services
from my_agent.config import load_settings
from my_agent.schemas import FailureRecord, PhotoRecord
from my_agent.schemas.query import (
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
)

CACHE_TTL_S = 30  # pick up photos saved by a running pipeline


@st.cache_resource(show_spinner=False)
def services() -> UiServices:
    """Build the services once per UI process."""
    return build_ui_services(load_settings())


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def search(query_json: str) -> PhotoPage:
    """Run a search; the query is passed as JSON so it caches reliably."""
    return services().catalog.search(PhotoQuery.model_validate_json(query_json))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def filter_options() -> FilterOptions:
    """Values for the sidebar filters."""
    return services().catalog.filter_options()


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def photo(path: str) -> PhotoRecord | None:
    """One photo by path."""
    return services().catalog.get(Path(path))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def near_duplicates(path: str) -> list[NearDuplicate]:
    """Photos that look like the given one."""
    record = services().catalog.get(Path(path))
    return services().catalog.near_duplicates(record) if record else []


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def stats() -> PhotoStats:
    """Totals and breakdowns."""
    return services().catalog.stats()


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def failures() -> list[FailureRecord]:
    """Every logged failure."""
    return services().failures.all_failures()


def refresh() -> None:
    """Drop cached query results so the next render reads fresh data."""
    st.cache_data.clear()
