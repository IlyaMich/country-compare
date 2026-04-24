from __future__ import annotations

import inspect

import pandas as pd
import pytest

from country_compare.prediction import (
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    build_prediction_result_summary,
)
from country_compare.services import AppContext
from country_compare.services.prediction_service import PredictionService


class InMemoryDatasetService:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe

    def load_dataframe(self) -> pd.DataFrame:
        return self.dataframe.copy(deep=True)


def _canonical_df() -> pd.DataFrame:
    rows = []
    values = {
        ("ISR", "gdp_per_capita"): [10.0, 20.0, 30.0, 40.0],
        ("FRA", "gdp_per_capita"): [8.0, 12.0, 16.0, 20.0],
        ("ISR", "unemployment_pct"): [8.0, 7.0, 6.0, 5.0],
        ("FRA", "unemployment_pct"): [9.0, 8.5, 8.0, 7.5],
    }
    country_names = {"ISR": "Israel", "FRA": "France"}
    metric_meta = {
        "gdp_per_capita": ("GDP per capita", "USD", True, "economy", "https://example.com/gdp"),
        "unemployment_pct": ("Unemployment", "pct", False, "labor", "https://example.com/unemployment"),
    }

    for (country_code, metric_id), series in values.items():
        metric_name, unit, higher_is_better, category, source_url = metric_meta[metric_id]
        for offset, value in enumerate(series):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_names[country_code],
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "value": value,
                    "year": 2020 + offset,
                    "unit": unit,
                    "source_name": "Example Source",
                    "source_url": source_url,
                    "higher_is_better": higher_is_better,
                    "category": category,
                    "dataset_version": "test-v1",
                    "region": "Example Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )

    return pd.DataFrame(rows)


def _service(dataframe: pd.DataFrame | None = None) -> PredictionService:
    resolved_dataframe = _canonical_df() if dataframe is None else dataframe
    return PredictionService(
        context=AppContext(),
        dataset_service=InMemoryDatasetService(resolved_dataframe),
    )


def test_prediction_method_catalog_includes_registered_builtins() -> None:
    catalog = _service().list_prediction_methods()
    method_ids = {item["method_id"] for item in catalog}

    assert {"last_observed", "linear_trend", "moving_average"}.issubset(method_ids)
    for item in catalog:
        assert item["display_name"]
        assert "description" in item
        assert "metadata" in item


def test_service_single_series_prediction_returns_expected_output() -> None:
    result = _service().run_single_metric_prediction(
        country_code="ISR",
        metric_id="gdp_per_capita",
        horizon_years=2,
        method=PredictionMethod.MOVING_AVERAGE,
    )

    assert result.ok
    assert result.error is None
    assert result.prediction_result is not None
    assert result.prediction_result.forecast_df["value"].tolist() == pytest.approx([30.0, 30.0])
    assert result.summary["forecast"]["row_count"] == 2
    assert result.summary["forecast_years"] == [2024, 2025]


def test_service_batch_prediction_preserves_partial_success_metadata() -> None:
    result = _service().run_single_metric_prediction_for_countries(
        metric_id="gdp_per_capita",
        country_codes=["ISR", "USA", "FRA"],
        horizon_years=1,
        fail_fast=False,
    )

    assert result.ok
    assert result.prediction_result is not None
    assert result.prediction_result.metadata["successful_series_count"] == 2
    assert result.prediction_result.metadata["failed_series_count"] == 1
    assert result.summary["diagnostics"]["status_counts"]["failed"] == 1


def test_service_predicted_comparison_delegates_to_bridge() -> None:
    result = _service().run_predicted_single_metric_comparison(
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        forecast_horizon=1,
        horizon_years=1,
        comparison_options={"normalization_method": "minmax"},
    )

    assert result.ok
    assert result.predicted_comparison_result is not None
    assert result.dataframe is not None
    assert result.dataframe["country_code"].tolist() == ["ISR", "FRA"]
    assert result.summary["selected_forecast_horizon"] == 1


def test_service_backtest_delegates_to_evaluation() -> None:
    dataframe = pd.concat(
        [
            _canonical_df(),
            pd.DataFrame(
                [
                    {
                        "country_code": "ISR",
                        "country_name": "Israel",
                        "metric_id": "gdp_per_capita",
                        "metric_name": "GDP per capita",
                        "value": 50.0,
                        "year": 2024,
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
                ]
            ),
        ],
        ignore_index=True,
    )

    result = _service(dataframe).run_backtest(
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.LINEAR_TREND,
        holdout_years=2,
    )

    assert result.ok
    assert result.backtest_result is not None
    assert result.summary["actual_vs_predicted"]["row_count"] == 2
    assert result.summary["metrics"]["method_used"] == "linear_trend"


def test_prediction_result_summary_does_not_mutate_dataframes() -> None:
    service_result = _service().run_single_metric_prediction(
        country_code="ISR",
        metric_id="gdp_per_capita",
        horizon_years=1,
    )
    prediction_result = service_result.prediction_result
    assert prediction_result is not None

    forecast_before = prediction_result.forecast_df.copy(deep=True)
    combined_before = prediction_result.combined_df.copy(deep=True)
    comparison_before = prediction_result.comparison_ready_df.copy(deep=True)

    summary = build_prediction_result_summary(prediction_result)

    assert summary["forecast"]["row_count"] == 1
    pd.testing.assert_frame_equal(prediction_result.forecast_df, forecast_before)
    pd.testing.assert_frame_equal(prediction_result.combined_df, combined_before)
    pd.testing.assert_frame_equal(prediction_result.comparison_ready_df, comparison_before)


def test_prediction_exception_translation_preserves_structured_fields() -> None:
    exc = PredictionException(
        PredictionErrorCode.MISSING_COUNTRY,
        "country_code 'USA' was not found",
        country_code="USA",
        metric_id="gdp_per_capita",
        details={"available_countries": ["ISR", "FRA"]},
    )

    service = _service()
    payload = service.translate_prediction_exception(exc)
    app_error = service.prediction_exception_to_app_error(exc)

    assert payload["code"] == "missing_country"
    assert payload["message"] == "country_code 'USA' was not found"
    assert payload["country_code"] == "USA"
    assert payload["metric_id"] == "gdp_per_capita"
    assert payload["details"] == {"available_countries": ["ISR", "FRA"]}

    assert app_error.code == "missing_country"
    assert app_error.user_message == "country_code 'USA' was not found"
    assert app_error.field_errors["country_code"] == "USA"
    assert app_error.field_errors["metric_id"] == "gdp_per_capita"


def test_service_returns_app_error_for_prediction_failure() -> None:
    result = _service().run_single_metric_prediction(
        country_code="USA",
        metric_id="gdp_per_capita",
        horizon_years=1,
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "missing_country"


def test_prediction_service_does_not_import_ui_or_rendering_dependencies() -> None:
    import country_compare.services.prediction_service as prediction_service_module
    import country_compare.prediction.summaries as summaries_module

    service_source = inspect.getsource(prediction_service_module)
    summaries_source = inspect.getsource(summaries_module)

    forbidden_terms = ("streamlit", "plotly", "matplotlib", "seaborn", "FastAPI")
    for term in forbidden_terms:
        assert term not in service_source
        assert term not in summaries_source