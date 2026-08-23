from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from country_compare.prediction import PredictionMethod
from country_compare.services.prediction_service import PredictionService


@dataclass
class DummyContext:
    metrics_config_path: Path = Path("config/metrics.yaml")
    scoring_config_path: Path = Path("config/scoring.yaml")
    store_backend: str = "parquet"
    store_path: Path | None = None
    debug: bool = False


class StubPredictionService(PredictionService):
    def __init__(self, dataframe: pd.DataFrame) -> None:
        super().__init__(context=DummyContext())
        self._dataframe = dataframe

    def _load_dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy(deep=True)


def _prediction_dataframe() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for year, value in zip(
        (2020, 2021, 2022, 2023),
        (10.0, 20.0, 30.0, 40.0),
        strict=True,
    ):
        rows.append(
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "oracle_metric",
                "metric_name": "Oracle Metric",
                "value": value,
                "year": year,
                "unit": "oracle_unit",
                "source_name": "Validation oracle",
                "source_url": "https://example.test/validation-oracle",
                "higher_is_better": True,
                "category": "validation",
                "dataset_version": "oracle-v1",
                "region": "Oracle Region",
                "income_group": "Oracle Income",
                "notes": None,
            }
        )

    # Present in the dataset but deliberately too sparse for linear_trend.
    rows.append(
        {
            "country_code": "CCC",
            "country_name": "Gamma",
            "metric_id": "oracle_metric",
            "metric_name": "Oracle Metric",
            "value": 500.0,
            "year": 2023,
            "unit": "oracle_unit",
            "source_name": "Validation oracle",
            "source_url": "https://example.test/validation-oracle",
            "higher_is_better": True,
            "category": "validation",
            "dataset_version": "oracle-v1",
            "region": "Oracle Region",
            "income_group": "Oracle Income",
            "notes": None,
        }
    )

    return pd.DataFrame(rows)


def test_pred_13_service_preserves_normal_prediction_diagnostics() -> None:
    service = StubPredictionService(_prediction_dataframe())

    result = service.run_single_metric_prediction(
        country_code="AAA",
        metric_id="oracle_metric",
        horizon_years=2,
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=PredictionMethod.LAST_OBSERVED,
        scenario_id="validation-normal",
    )

    assert result.ok is True
    assert result.error is None

    assert result.diagnostics["count"] == 1
    assert result.diagnostics["status_counts"] == {"ok": 1}
    assert result.diagnostics["warnings"] == []
    assert result.diagnostics["errors"] == []

    diagnostic = result.diagnostics["items"][0]

    assert diagnostic["status"] == "ok"
    assert diagnostic["country_code"] == "AAA"
    assert diagnostic["metric_id"] == "oracle_metric"
    assert diagnostic["method_requested"] == "linear_trend"
    assert diagnostic["method_used"] == "linear_trend"
    assert diagnostic["fallback_used"] is False
    assert diagnostic["history_observation_count"] == 4
    assert diagnostic["training_start_year"] == 2020
    assert diagnostic["training_end_year"] == 2023
    assert diagnostic["forecast_origin_year"] == 2023
    assert diagnostic["warnings"] == []
    assert diagnostic["errors"] == []
    assert diagnostic["messages"] == []

    assert result.metadata["method_requested"] == "linear_trend"
    assert result.metadata["method_used"] == "linear_trend"
    assert result.metadata["fallback_used"] is False

    assert result.summary["request"]["scenario_id"] == "validation-normal"
    assert set(result.dataframe["scenario_id"]) == {"validation-normal"}


def test_pred_13_service_preserves_fallback_reason_and_history_bounds() -> None:
    service = StubPredictionService(_prediction_dataframe())

    result = service.run_single_metric_prediction(
        country_code="AAA",
        metric_id="oracle_metric",
        horizon_years=2,
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=PredictionMethod.LAST_OBSERVED,
        history_start_year=2022,
        scenario_id="validation-fallback",
    )

    assert result.ok is True

    assert result.diagnostics["status_counts"] == {"warning": 1}

    diagnostic = result.diagnostics["items"][0]

    assert diagnostic["status"] == "warning"
    assert diagnostic["method_requested"] == "linear_trend"
    assert diagnostic["method_used"] == "last_observed"
    assert diagnostic["fallback_used"] is True
    assert diagnostic["history_observation_count"] == 2
    assert diagnostic["training_start_year"] == 2022
    assert diagnostic["training_end_year"] == 2023
    assert diagnostic["forecast_origin_year"] == 2023

    assert any(
        "used fallback method 'last_observed'" in warning
        for warning in diagnostic["warnings"]
    )
    assert any(
        "requires at least three observations" in warning
        for warning in diagnostic["warnings"]
    )

    assert diagnostic["messages"] == diagnostic["warnings"]

    assert result.metadata["method_requested"] == "linear_trend"
    assert result.metadata["method_used"] == "last_observed"
    assert result.metadata["fallback_used"] is True

    assert result.warnings == result.diagnostics["warnings"]

    assert result.summary["request"]["scenario_id"] == "validation-fallback"
    assert set(result.dataframe["scenario_id"]) == {"validation-fallback"}


def test_pred_13_service_preserves_failed_series_diagnostics() -> None:
    service = StubPredictionService(_prediction_dataframe())

    result = service.run_single_metric_prediction_for_countries(
        metric_id="oracle_metric",
        country_codes=["AAA", "CCC"],
        horizon_years=2,
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=None,
        include_actuals=False,
        fail_fast=False,
        scenario_id="validation-partial-failure",
    )

    assert result.ok is True

    assert result.diagnostics["count"] == 2
    assert result.diagnostics["status_counts"] == {
        "ok": 1,
        "failed": 1,
    }

    diagnostics_by_country = {
        item["country_code"]: item for item in result.diagnostics["items"]
    }

    aaa = diagnostics_by_country["AAA"]

    assert aaa["status"] == "ok"
    assert aaa["method_requested"] == "linear_trend"
    assert aaa["method_used"] == "linear_trend"
    assert aaa["fallback_used"] is False

    ccc = diagnostics_by_country["CCC"]

    assert ccc["status"] == "failed"
    assert ccc["method_requested"] == "linear_trend"
    assert ccc["method_used"] is None
    assert ccc["fallback_used"] is False
    assert len(ccc["errors"]) == 1

    error = ccc["errors"][0]

    assert error["code"] == "insufficient_history"
    assert error["country_code"] == "CCC"
    assert error["metric_id"] == "oracle_metric"
    assert "requires at least three observations" in error["message"]

    assert ccc["messages"] == [error["message"]]

    assert result.metadata["successful_series_count"] == 1
    assert result.metadata["failed_series_count"] == 1
    assert result.metadata["all_series_failed"] is False

    assert result.summary["request"]["scenario_id"] == ("validation-partial-failure")
