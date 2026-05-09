from __future__ import annotations

import pytest

from country_compare.api.settings import ApiSettings


def test_api_settings_reads_limits_and_auth_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_RECORDS", "25")
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_COUNTRIES", "3")
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_METRICS", "4")
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_HORIZON_YEARS", "5")
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS", "6")
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_TOP_N", "7")
    monkeypatch.setenv("COUNTRY_COMPARE_API_KEY", "  secret  ")

    settings = ApiSettings.from_env()

    assert settings.max_records == 25
    assert settings.max_countries == 3
    assert settings.max_metrics == 4
    assert settings.max_horizon_years == 5
    assert settings.max_holdout_years == 6
    assert settings.max_top_n == 7
    assert settings.api_key == "secret"


def test_api_settings_uses_default_cors_origins_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COUNTRY_COMPARE_API_CORS_ORIGINS", raising=False)

    settings = ApiSettings.from_env()

    assert settings.cors_origins == ("http://localhost:8501",)


def test_api_settings_allows_empty_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_API_CORS_ORIGINS", "")

    settings = ApiSettings.from_env()

    assert settings.cors_origins == ()


def test_api_settings_trims_configured_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "COUNTRY_COMPARE_API_CORS_ORIGINS",
        " https://app.example.com, http://localhost:8501 ,, ",
    )

    settings = ApiSettings.from_env()

    assert settings.cors_origins == (
        "https://app.example.com",
        "http://localhost:8501",
    )


def test_api_settings_rejects_non_positive_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_API_MAX_COUNTRIES", "0")

    with pytest.raises(ValueError, match="COUNTRY_COMPARE_API_MAX_COUNTRIES"):
        ApiSettings.from_env()
