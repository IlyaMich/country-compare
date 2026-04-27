from __future__ import annotations

from typing import Final

SIDEBAR_TITLE: Final[str] = "Country Compare"
PAGE_RADIO_LABEL: Final[str] = "Page"
DEBUG_CHECKBOX_LABEL: Final[str] = "Debug mode"
RESERVED_PAGE_INFO: Final[str] = "This page is reserved for a later UI phase."

BACKEND_CAPTION_PREFIX: Final[str] = "Backend"
METRICS_CONFIG_CAPTION_PREFIX: Final[str] = "Metrics config"
SCORING_CONFIG_CAPTION_PREFIX: Final[str] = "Scoring config"


def backend_caption(store_backend: str) -> str:
    return f"{BACKEND_CAPTION_PREFIX}: {store_backend}"


def metrics_config_caption(path: object) -> str:
    return f"{METRICS_CONFIG_CAPTION_PREFIX}: {path}"


def scoring_config_caption(path: object) -> str:
    return f"{SCORING_CONFIG_CAPTION_PREFIX}: {path}"
