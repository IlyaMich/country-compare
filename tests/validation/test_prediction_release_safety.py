from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd

from country_compare.prediction import (
    PredictionDiagnosticStatus,
    SingleMetricPredictionRequest,
    list_available_prediction_methods,
    predict_single_metric,
)

DATA_CORRECTNESS_PATH_ENV = "COUNTRY_COMPARE_DATA_CORRECTNESS_PATH"
DEFAULT_RELEASE_DATASET_PATH = Path("data/processed/metrics.parquet")

NON_DETERMINISTIC_METHODS = {
    "llm_forecast",
}

CORE_DETERMINISTIC_METHODS = {
    "last_observed",
    "moving_average",
    "linear_trend",
    "holt_linear",
}


def _release_dataset_path() -> Path:
    configured_path = os.environ.get(DATA_CORRECTNESS_PATH_ENV)

    path = Path(configured_path) if configured_path else DEFAULT_RELEASE_DATASET_PATH

    assert path.exists(), (
        "PRED-22 requires the release parquet. "
        f"Expected it at {path!s}, or set "
        f"{DATA_CORRECTNESS_PATH_ENV}."
    )

    return path


def _load_release_dataframe() -> pd.DataFrame:
    dataframe = pd.read_parquet(_release_dataset_path())

    required_columns = {
        "country_code",
        "metric_id",
        "year",
        "value",
    }

    missing = required_columns.difference(dataframe.columns)

    assert (
        not missing
    ), "release dataset is missing columns required by PRED-22: " + ", ".join(
        sorted(missing)
    )

    return dataframe


def _deterministic_method_ids() -> list[str]:
    method_catalog = list_available_prediction_methods()

    advertised = {str(method["method_id"]) for method in method_catalog}

    assert CORE_DETERMINISTIC_METHODS.issubset(advertised)

    return sorted(
        method_id
        for method_id in advertised
        if method_id not in NON_DETERMINISTIC_METHODS
    )


def _representative_release_series(
    dataframe: pd.DataFrame,
    *,
    series_count: int = 3,
) -> list[tuple[str, str]]:
    working = dataframe.loc[
        :,
        [
            "country_code",
            "metric_id",
            "year",
            "value",
        ],
    ].copy()

    working["_year_numeric"] = pd.to_numeric(
        working["year"],
        errors="coerce",
    )
    working["_value_numeric"] = pd.to_numeric(
        working["value"],
        errors="coerce",
    )

    working = working.loc[
        working["_year_numeric"].notna() & working["_value_numeric"].notna()
    ].copy()

    working = working.loc[
        working["_value_numeric"].map(lambda value: math.isfinite(float(value)))
    ].copy()

    coverage = working.groupby(
        ["metric_id", "country_code"],
        as_index=False,
    ).agg(
        observation_count=("_year_numeric", "count"),
        distinct_years=("_year_numeric", "nunique"),
        year_min=("_year_numeric", "min"),
        year_max=("_year_numeric", "max"),
    )

    # Eight observations is sufficient for the strictest currently
    # advertised deterministic method: elasticnet_trend.
    eligible = coverage.loc[
        coverage["observation_count"].ge(8) & coverage["distinct_years"].ge(8)
    ].copy()

    eligible = eligible.sort_values(
        by=[
            "observation_count",
            "metric_id",
            "country_code",
        ],
        ascending=[False, True, True],
        kind="mergesort",
    )

    representatives: list[tuple[str, str]] = []
    selected_metrics: set[str] = set()

    for row in eligible.itertuples(index=False):
        metric_id = str(row.metric_id)
        country_code = str(row.country_code)

        # Prefer different metrics so the safety sweep is not three
        # countries from the same underlying indicator.
        if metric_id in selected_metrics:
            continue

        representatives.append((country_code, metric_id))
        selected_metrics.add(metric_id)

        if len(representatives) == series_count:
            break

    assert len(representatives) == series_count, (
        "PRED-22 could not find enough release series with at least "
        "8 finite observations and 8 distinct years. "
        f"Found {len(representatives)}, expected {series_count}."
    )

    return representatives


def test_pred_22_advertised_deterministic_methods_are_numerically_safe_on_release_series() -> (
    None
):
    dataframe = _load_release_dataframe()

    method_ids = _deterministic_method_ids()
    representative_series = _representative_release_series(
        dataframe,
    )

    assert method_ids

    for method_id in method_ids:
        for country_code, metric_id in representative_series:
            case = (
                f"method={method_id}, "
                f"country={country_code}, "
                f"metric={metric_id}"
            )

            source_series = dataframe.loc[
                dataframe["country_code"].astype("string").str.upper().eq(country_code)
                & dataframe["metric_id"].astype("string").eq(metric_id)
            ].copy()

            source_years = pd.to_numeric(
                source_series["year"],
                errors="coerce",
            ).dropna()

            assert not source_years.empty, case

            forecast_origin_year = int(source_years.max())

            result = predict_single_metric(
                dataframe,
                SingleMetricPredictionRequest(
                    country_code=country_code,
                    metric_id=metric_id,
                    horizon_years=3,
                    method=method_id,
                    fallback_method=None,
                    include_actuals=False,
                    scenario_id="validation-release-safety",
                ),
            )

            forecast = result.forecast_df

            # Exactly the requested horizon.
            assert len(forecast.index) == 3, case

            expected_years = [
                forecast_origin_year + 1,
                forecast_origin_year + 2,
                forecast_origin_year + 3,
            ]

            assert forecast["year"].tolist() == expected_years, case
            assert forecast["year"].is_unique, case
            assert forecast["year"].is_monotonic_increasing, case

            assert forecast["forecast_horizon"].tolist() == [
                1,
                2,
                3,
            ], case

            # Every value must remain numeric and finite.
            forecast_values = pd.to_numeric(
                forecast["value"],
                errors="coerce",
            )

            assert forecast_values.notna().all(), case
            assert all(
                math.isfinite(float(value)) for value in forecast_values.tolist()
            ), case

            # Identity must remain attached to the correct series.
            assert set(forecast["country_code"]) == {country_code}, case
            assert set(forecast["metric_id"]) == {metric_id}, case
            assert set(forecast["prediction_method"]) == {method_id}, case
            assert set(forecast["scenario_id"]) == {"validation-release-safety"}, case

            assert set(forecast["row_type"]) == {"predicted"}, case
            assert set(forecast["is_predicted"]) == {True}, case

            # A single prediction operation has one stable run identity.
            assert forecast["prediction_run_id"].nunique() == 1, case
            assert forecast["prediction_created_at"].nunique() == 1, case

            diagnostic = result.diagnostics[0]

            assert diagnostic.status in {
                PredictionDiagnosticStatus.OK,
                PredictionDiagnosticStatus.WARNING,
            }, case

            assert diagnostic.method_requested == method_id, case
            assert diagnostic.method_used == method_id, case
            assert diagnostic.fallback_used is False, case
            assert diagnostic.errors == [], case

            assert diagnostic.forecast_origin_year == forecast_origin_year, case

            # The canonical-like comparison representation must remain
            # numerically faithful to the forecast rows.
            comparison_ready = result.comparison_ready_df

            assert comparison_ready["year"].tolist() == (
                forecast["year"].tolist()
            ), case

            assert comparison_ready["value"].tolist() == (
                forecast["value"].tolist()
            ), case

            assert (
                comparison_ready["country_code"].tolist()
                == forecast["country_code"].tolist()
            ), case

            assert (
                comparison_ready["metric_id"].tolist() == forecast["metric_id"].tolist()
            ), case
