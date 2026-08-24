from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd
import pytest

from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    predict_single_metric,
)
from country_compare.prediction.llm import forecasters as llm_forecasters
from country_compare.prediction.llm.client import (
    LLMForecastPoint,
    LLMForecastRequest,
    LLMForecastResponse,
    LLMForecastResponseParseError,
    llm_response_from_json,
)
from country_compare.prediction.llm.forecasters import (
    set_llm_forecast_client_override,
)
from country_compare.prediction.registry import clear_forecasters, list_forecasters


@dataclass
class FakeLLMForecastClient:
    response: LLMForecastResponse | None = None
    error: Exception | None = None
    calls: list[LLMForecastRequest] = field(default_factory=list)

    def forecast(self, request: LLMForecastRequest) -> LLMForecastResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error

        if self.response is None:
            raise RuntimeError("fake client response was not configured")

        return self.response


class _UnavailableLLMServiceClient:
    def is_available(self) -> bool:
        raise RuntimeError("simulated unavailable private LLM service")


@pytest.fixture(autouse=True)
def reset_llm_forecast_state(monkeypatch: pytest.MonkeyPatch):
    set_llm_forecast_client_override(None)
    monkeypatch.delenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_MODEL", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_BASELINE_METHOD", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_URL", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_MAX_SERIES_PER_REQUEST", raising=False)
    monkeypatch.delenv(
        "COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT",
        raising=False,
    )
    clear_forecasters()

    yield

    set_llm_forecast_client_override(None)
    monkeypatch.delenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_MODEL", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_BASELINE_METHOD", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_URL", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("COUNTRY_COMPARE_LLM_MAX_SERIES_PER_REQUEST", raising=False)
    monkeypatch.delenv(
        "COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT",
        raising=False,
    )
    clear_forecasters()


def _canonical_df() -> pd.DataFrame:
    rows = []
    for year, value in zip(
        (2020, 2021, 2022, 2023),
        (10.0, 20.0, 30.0, 40.0),
        strict=True,
    ):
        rows.append(
            {
                "country_code": "DEU",
                "country_name": "Germany",
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "value": value,
                "year": year,
                "unit": "USD",
                "source_name": "Example Source",
                "source_url": "https://example.com/gdp",
                "higher_is_better": True,
                "category": "economy",
                "dataset_version": "test-v1",
                "region": "Example Region",
                "income_group": "High income",
                "notes": None,
            }
        )

    return pd.DataFrame(rows)


def test_llm_forecast_is_hidden_and_rejected_when_disabled() -> None:
    fake_client = FakeLLMForecastClient(
        response=LLMForecastResponse(
            forecast_points=[LLMForecastPoint(year=2024, value=41.0)]
        )
    )
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    assert "llm_forecast" not in list_forecasters()

    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(
            _canonical_df(),
            SingleMetricPredictionRequest(
                country_code="DEU",
                metric_id="gdp_per_capita",
                horizon_years=1,
                method=PredictionMethod.LLM_FORECAST,
            ),
        )

    assert exc_info.value.code == PredictionErrorCode.UNSUPPORTED_METHOD
    assert fake_client.calls == []


@pytest.mark.parametrize(
    ("service_url", "service_token"),
    [
        ("", "test-token"),
        ("http://llm-service:8001", ""),
    ],
)
def test_llm_02_enabled_but_incomplete_remote_config_hides_llm_forecast(
    monkeypatch: pytest.MonkeyPatch,
    service_url: str,
    service_token: str,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_SERVICE_URL", service_url)
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_SERVICE_TOKEN", service_token)

    clear_forecasters()

    available_methods = list_forecasters()

    assert "llm_forecast" not in available_methods
    assert "last_observed" in available_methods


def test_llm_07_successful_llm_forecast_preserves_structural_invariants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_MODEL", "mock-model")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_BASELINE_METHOD", "last_observed")

    fake_client = FakeLLMForecastClient(
        response=LLMForecastResponse(
            forecast_points=[
                LLMForecastPoint(year=2024, value=42.0),
                LLMForecastPoint(year=2025, value=43.0),
            ],
            rationale="Mocked bounded adjustment.",
            assumptions=["History remains directionally stable."],
            warnings=["Mock warning."],
            raw_provider_metadata={"test_provider": True},
        )
    )
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    assert "llm_forecast" in list_forecasters()

    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="DEU",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    forecast_df = result.forecast_df

    assert len(forecast_df.index) == 2
    assert forecast_df["year"].tolist() == [2024, 2025]

    assert forecast_df["country_code"].unique().tolist() == ["DEU"]
    assert forecast_df["metric_id"].unique().tolist() == ["gdp_per_capita"]

    assert all(math.isfinite(float(value)) for value in forecast_df["value"].tolist())

    assert forecast_df["prediction_method"].unique().tolist() == ["llm_forecast"]

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0].prompt_version == "llm_forecast_v1"
    assert fake_client.calls[0].baseline_forecast == [
        {"year": 2024, "value": 40.0},
        {"year": 2025, "value": 40.0},
    ]

    assert result.forecast_df["year"].tolist() == [2024, 2025]
    assert result.forecast_df["value"].tolist() == pytest.approx([42.0, 43.0])
    assert result.forecast_df["prediction_method"].unique().tolist() == ["llm_forecast"]

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_used == "llm_forecast"
    assert diagnostic.fallback_used is False
    assert any("experimental" in warning for warning in diagnostic.warnings)

    info = result.forecaster_info[0]
    assert info.method_id == "llm_forecast"
    assert info.metadata["experimental"] is True
    assert info.metadata["provider"] == "mock"
    assert info.metadata["model"] == "mock-model"
    assert info.metadata["baseline_method"] == "last_observed"
    assert info.metadata["validation_status"] == "valid"
    assert info.metadata["fallback_used"] is False
    assert info.metadata["rationale"] == "Mocked bounded adjustment."


def test_llm_forecast_falls_back_to_baseline_on_wrong_horizon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_MODEL", "mock-model")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_BASELINE_METHOD", "last_observed")

    fake_client = FakeLLMForecastClient(
        response=LLMForecastResponse(
            forecast_points=[LLMForecastPoint(year=2024, value=42.0)]
        )
    )
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="DEU",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    assert len(fake_client.calls) == 1
    assert result.forecast_df["year"].tolist() == [2024, 2025]
    assert result.forecast_df["value"].tolist() == pytest.approx([40.0, 40.0])

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert any(
        "baseline forecast was returned" in warning for warning in diagnostic.warnings
    )

    info = result.forecaster_info[0]
    assert info.metadata["validation_status"] == "fallback"
    assert info.metadata["fallback_used"] is True
    assert info.metadata["fallback_method"] == "last_observed"
    assert info.metadata["failure_reason_code"] == "llm_forecast_failed"

    diagnostic_messages = info.metadata["diagnostic_messages"]
    assert diagnostic_messages["user"]
    assert diagnostic_messages["operator"] == [
        "See backend logs for the LLM forecast fallback reason."
    ]

    serialized_metadata = str(info.metadata)
    assert "forecast point count" not in serialized_metadata
    assert (
        "LLM response forecast point count did not match requested horizon"
        not in serialized_metadata
    )


def test_llm_forecast_falls_back_when_provider_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_MODEL", "mock-model")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_BASELINE_METHOD", "last_observed")

    fake_client = FakeLLMForecastClient(error=TimeoutError("mock timeout"))
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="DEU",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    assert result.forecast_df["value"].tolist() == pytest.approx([40.0])

    metadata = result.forecaster_info[0].metadata

    assert metadata["fallback_used"] is True
    assert metadata["fallback_method"] == "last_observed"
    assert metadata["failure_reason_code"] == "llm_forecast_failed"

    diagnostic_messages = metadata["diagnostic_messages"]
    assert diagnostic_messages["user"]
    assert diagnostic_messages["operator"] == [
        "See backend logs for the LLM forecast fallback reason."
    ]

    serialized_metadata = str(metadata)
    assert "mock timeout" not in serialized_metadata
    assert "TimeoutError" not in serialized_metadata


def test_llm_response_from_json_parses_valid_payload() -> None:
    response = llm_response_from_json("""
        {
          "forecast_points": [
            {"year": 2024, "value": 42.5}
          ],
          "rationale": "Test rationale",
          "assumptions": ["Test assumption"],
          "warnings": ["Test warning"],
          "raw_provider_metadata": {"provider": "test"}
        }
        """)

    assert response.forecast_points == [LLMForecastPoint(year=2024, value=42.5)]
    assert response.rationale == "Test rationale"
    assert response.assumptions == ["Test assumption"]
    assert response.warnings == ["Test warning"]
    assert response.raw_provider_metadata == {"provider": "test"}


def test_llm_response_from_json_rejects_invalid_json() -> None:
    with pytest.raises(LLMForecastResponseParseError):
        llm_response_from_json("{not json")


def test_llm_03_unavailable_service_hides_llm_but_preserves_deterministic_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_SERVICE_URL",
        "http://llm-service:8001",
    )
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_SERVICE_TOKEN",
        "test-token",
    )

    monkeypatch.setattr(
        llm_forecasters,
        "_remote_client_from_settings",
        lambda *args, **kwargs: _UnavailableLLMServiceClient(),
    )

    clear_forecasters()

    available_methods = list_forecasters()

    assert "llm_forecast" not in available_methods
    assert "last_observed" in available_methods
    assert "linear_trend" in available_methods


def test_llm_08_accepts_adjustments_at_configured_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_MODEL", "mock-model")
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_BASELINE_METHOD",
        "last_observed",
    )
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT",
        "5",
    )

    fake_client = FakeLLMForecastClient(
        response=LLMForecastResponse(
            forecast_points=[
                LLMForecastPoint(year=2024, value=42.0),
                LLMForecastPoint(year=2025, value=38.0),
            ]
        )
    )
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="DEU",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    assert len(fake_client.calls) == 1

    baseline = fake_client.calls[0].baseline_forecast
    assert baseline == [
        {"year": 2024, "value": 40.0},
        {"year": 2025, "value": 40.0},
    ]

    actual_values = result.forecast_df["value"].tolist()

    for value, baseline_point in zip(
        actual_values,
        baseline,
        strict=True,
    ):
        baseline_value = float(baseline_point["value"])
        allowed_delta = abs(baseline_value) * 0.05

        assert abs(float(value) - baseline_value) <= (allowed_delta + 1e-12)

    assert actual_values == pytest.approx([42.0, 38.0])

    metadata = result.forecaster_info[0].metadata
    assert metadata["max_adjustment_pct"] == pytest.approx(5.0)
    assert metadata["validation_status"] == "valid"
    assert metadata["fallback_used"] is False


def test_llm_08_out_of_bound_adjustment_falls_back_to_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_ENABLE_LLM_FORECAST", "true")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_MODEL", "mock-model")
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_BASELINE_METHOD",
        "last_observed",
    )
    monkeypatch.setenv(
        "COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT",
        "5",
    )

    # Baseline is 40.0. Five percent permits at most +/-2.0.
    # 42.01 is therefore intentionally outside the contract.
    fake_client = FakeLLMForecastClient(
        response=LLMForecastResponse(
            forecast_points=[
                LLMForecastPoint(year=2024, value=42.01),
            ]
        )
    )
    set_llm_forecast_client_override(fake_client)
    clear_forecasters()

    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="DEU",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    assert len(fake_client.calls) == 1

    assert result.forecast_df["year"].tolist() == [2024]
    assert result.forecast_df["value"].tolist() == pytest.approx([40.0])

    metadata = result.forecaster_info[0].metadata

    assert metadata["validation_status"] == "fallback"
    assert metadata["fallback_used"] is True
    assert metadata["fallback_method"] == "last_observed"
    assert metadata["failure_reason_code"] == "llm_forecast_failed"

    assert any(
        "baseline forecast was returned" in warning
        for warning in result.diagnostics[0].warnings
    )
