from __future__ import annotations

from doctest import debug
from pathlib import Path

import streamlit as st

from country_compare.services import AppContext, AppFacade
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.config_service import ConfigService
from country_compare.services.dataset_service import DatasetService
from country_compare.services.presentation_service import PresentationService
from country_compare.services.prediction_service import PredictionService
from country_compare.settings import AppSettings, load_app_settings
from country_compare.ui import state


def build_app_context(
    *,
    settings: AppSettings | None = None,
    metrics_config_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    store_backend: str | None = None,
    store_path: str | Path | None = None,
    debug: bool | None = None,
) -> AppContext:
 base = settings or load_app_settings(
  metrics_config_path=metrics_config_path,
  scoring_config_path=scoring_config_path,
  store_backend=store_backend,
  store_path=store_path,
  debug=debug,
 )
 return AppContext(
  metrics_config_path=base.paths.metrics_config_path,
  scoring_config_path=base.paths.scoring_config_path,
  store_backend=base.paths.store_backend,
  store_path=base.paths.store_path,
  audit_dir=base.paths.audit_dir,
  export_dir=base.paths.export_dir,
  debug=base.debug,
  settings=base,
)


@st.cache_resource(show_spinner=False)
def _build_facade_cached(context: AppContext) -> AppFacade:
    return AppFacade(context)


@st.cache_resource(show_spinner=False)
def _build_ui_services_cached(context: AppContext) -> dict[str, object]:
    dataset_service = DatasetService(context=context)
    config_service = ConfigService(context=context, dataset_service=dataset_service)
    comparison_service = ComparisonService(
        context=context,
        dataset_service=dataset_service,
        config_service=config_service,
    )
    prediction_service = PredictionService(
        context=context,
        dataset_service=dataset_service,
        config_service=config_service,
    )
    presentation_service = PresentationService()
    return {
        "context": context,
        "dataset_service": dataset_service,
        "config_service": config_service,
        "comparison_service": comparison_service,
        "prediction_service": prediction_service,
        "presentation_service": presentation_service,
    }


def get_ui_services(context: AppContext) -> dict[str, object]:
    return _build_ui_services_cached(context)


def get_phase_b_services(context: AppContext) -> dict[str, object]:
    return get_ui_services(context)


def refresh_cached_services() -> None:
    _build_facade_cached.clear()
    _build_ui_services_cached.clear()


def bootstrap_app(
    *,
    settings: AppSettings | None = None,
    metrics_config_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    store_backend: str | None = None,
    store_path: str | Path | None = None,
    debug: bool | None = None,
) -> tuple[AppContext, AppFacade]:
    context = build_app_context(
        settings=settings,
        metrics_config_path=metrics_config_path,
        scoring_config_path=scoring_config_path,
        store_backend=store_backend,
        store_path=store_path,
        debug=debug,
    )
    state.initialize_session_state(default_debug=context.debug)
    facade = _build_facade_cached(context)
    return context, facade
