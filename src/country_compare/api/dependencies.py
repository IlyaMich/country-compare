from __future__ import annotations

from functools import lru_cache

from country_compare.services.app_context import AppContext
from country_compare.services.facade import AppFacade


@lru_cache(maxsize=1)
def get_app_context() -> AppContext:
    """Return the cached app context used by API route dependencies."""

    return AppContext.from_env()


@lru_cache(maxsize=1)
def get_app_facade() -> AppFacade:
    """Return the cached facade used by API route dependencies."""

    return AppFacade(get_app_context())
