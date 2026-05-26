from __future__ import annotations

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
                "country_code": "ISR",
                "country_name": "Israel",
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
                country_code="ISR",
                metric_id="gdp_per_capita",
                horizon_years=1,
                method=PredictionMethod.LLM_FORECAST,
            ),
        )

    assert exc_info.value.code == PredictionErrorCode.UNSUPPORTED_METHOD
    assert fake_client.calls == []


def test_llm_forecast_accepts_valid_mocked_response(
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
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

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
            country_code="ISR",
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
        "returned the validated baseline forecast" in warning
        for warning in diagnostic.warnings
    )

    info = result.forecaster_info[0]
    assert info.metadata["validation_status"] == "fallback"
    assert info.metadata["fallback_used"] is True
    assert info.metadata["fallback_method"] == "last_observed"
    assert "forecast point count" in str(info.metadata["failure_reason"])


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
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.LLM_FORECAST,
        ),
    )

    assert result.forecast_df["value"].tolist() == pytest.approx([40.0])
    assert result.forecaster_info[0].metadata["fallback_used"] is True
    assert "mock timeout" in str(result.forecaster_info[0].metadata["failure_reason"])


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
