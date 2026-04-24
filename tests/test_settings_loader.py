from __future__ import annotations

from pathlib import Path

from country_compare.settings import load_app_settings


def test_load_app_settings_applies_environment_overrides(monkeypatch):
    monkeypatch.setenv("COUNTRY_COMPARE_METRICS_CONFIG", "config/metrics.yaml")
    monkeypatch.setenv("COUNTRY_COMPARE_DEBUG", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_UI_PAGE_TITLE", "Custom Country Compare")
    monkeypatch.setenv("COUNTRY_COMPARE_MAX_PREDICTION_HORIZON", "7")

    settings = load_app_settings(app_config_path="missing-app-settings.yaml")

    assert settings.paths.metrics_config_path == Path("config/metrics.yaml")
    assert settings.debug is True
    assert settings.ui.page_title == "Custom Country Compare"
    assert settings.prediction.max_horizon_years == 7


def test_explicit_settings_override_environment(monkeypatch):
    monkeypatch.setenv("COUNTRY_COMPARE_STORE_BACKEND", "parquet")

    settings = load_app_settings(
        app_config_path="missing-app-settings.yaml",
        store_backend="custom_backend",
    )

    assert settings.paths.store_backend == "custom_backend"