from __future__ import annotations

from pathlib import Path

import streamlit as st

from country_compare.services import AppContext, AppFacade
from country_compare.ui import state


def build_app_context(
    *,
    metrics_config_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    store_backend: str | None = None,
    store_path: str | Path | None = None,
    debug: bool | None = None,
) -> AppContext:
    base = AppContext.from_env()
    return AppContext(
        metrics_config_path=Path(metrics_config_path) if metrics_config_path is not None else base.metrics_config_path,
        scoring_config_path=Path(scoring_config_path) if scoring_config_path is not None else base.scoring_config_path,
        store_backend=store_backend or base.store_backend,
        store_path=Path(store_path) if store_path is not None else base.store_path,
        debug=base.debug if debug is None else debug,
    )


@st.cache_resource(show_spinner=False)
def _build_facade_cached(context: AppContext) -> AppFacade:
    return AppFacade(context)


@st.cache_resource(show_spinner=False)
def _build_ui_services_cached(context: AppContext) -> dict[str, object]:
    facade = _build_facade_cached(context)
    return {
        "context": context,
        "facade": facade,
        "dataset_service": facade.dataset,
        "config_service": facade.config,
        "comparison_service": facade.comparison,
        "presentation_service": facade.presentation,
    }


def get_app_facade(context: AppContext) -> AppFacade:
    return _build_facade_cached(context)


def get_ui_services(context: AppContext) -> dict[str, object]:
    return _build_ui_services_cached(context)


def get_phase_b_services(context: AppContext) -> dict[str, object]:
    """Backward-compatible alias retained for existing imports."""
    return get_ui_services(context)


def refresh_cached_services() -> None:
    _build_facade_cached.clear()
    _build_ui_services_cached.clear()


def bootstrap_app(
    *,
    metrics_config_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    store_backend: str | None = None,
    store_path: str | Path | None = None,
    debug: bool | None = None,
) -> tuple[AppContext, AppFacade]:
    context = build_app_context(
        metrics_config_path=metrics_config_path,
        scoring_config_path=scoring_config_path,
        store_backend=store_backend,
        store_path=store_path,
        debug=debug,
    )
    state.initialize_session_state(default_debug=context.debug)
    facade = _build_facade_cached(context)
    return context, facade
