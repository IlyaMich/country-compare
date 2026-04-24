from __future__ import annotations

SIDEBAR_TITLE = "Country Compare"
PAGE_RADIO_LABEL = "Page"
DEBUG_CHECKBOX_LABEL = "Debug mode"
RESERVED_PAGE_INFO = "This page is reserved for a later UI phase."


def backend_caption(store_backend: str) -> str:
    return f"Backend: {store_backend}"


def metrics_config_caption(path: object) -> str:
    return f"Metrics config: {path}"


def scoring_config_caption(path: object) -> str:
    return f"Scoring config: {path}"