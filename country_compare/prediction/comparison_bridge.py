from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from country_compare.comparison.multi_metric import (
    ComparisonError as MultiComparisonError,
)
from country_compare.comparison.multi_metric import compare_countries
from country_compare.comparison.single_metric import (
    ComparisonError as SingleComparisonError,
)
from country_compare.comparison.single_metric import compare_metric
from country_compare.config.models import ScoringConfig, YearStrategy
from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    PredictedComparisonResult,
    PredictionMethod,
    PredictionResult,
)
from country_compare.prediction.multi_metric import (
    predict_metric_country_grid,
    predict_single_metric_for_countries,
)
from country_compare.prediction.output import FORECAST_HORIZON_COLUMN, ROW_TYPE_COLUMN

YEAR_COLUMN = "year"


def compare_predicted_single_metric(
    canonical_df: pd.DataFrame,
    *,
    metric_id: str,
    country_codes: Iterable[str],
    forecast_year: int | None = None,
    forecast_horizon: int | None = None,
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    comparison_options: Mapping[str, object] | None = None,
) -> PredictedComparisonResult:
    resolved_country_codes = list(country_codes)
    prediction_result = predict_single_metric_for_countries(
        canonical_df,
        metric_id=metric_id,
        country_codes=resolved_country_codes,
        horizon_years=horizon_years,
        method=method,
        fallback_method=fallback_method,
    )
    selected_df, selection = _select_predicted_rows(
        prediction_result,
        forecast_year=forecast_year,
        forecast_horizon=forecast_horizon,
        horizon_years=horizon_years,
    )
    comparison_kwargs = dict(comparison_options or {})
    comparison_kwargs.update(
        {
            "metric_id": metric_id,
            "countries_include": resolved_country_codes,
            "year_strategy": selection["comparison_year_strategy"],
            "target_year": selection["comparison_target_year"],
        }
    )
    try:
        comparison_df = compare_metric(selected_df, **comparison_kwargs)
    except SingleComparisonError as exc:
        raise PredictionException(
            PredictionErrorCode.COMPARISON_BRIDGE_FAILED,
            str(exc),
            metric_id=metric_id,
            details={"selection": selection},
        ) from exc
    return PredictedComparisonResult(
        comparison_df=comparison_df,
        prediction_result=prediction_result,
        diagnostics=prediction_result.diagnostics,
        selected_forecast_year=selection["selected_forecast_year"],
        selected_forecast_horizon=selection["selected_forecast_horizon"],
        metadata=selection,
    )


def compare_predicted_multi_metric(
    canonical_df: pd.DataFrame,
    *,
    metric_ids: Iterable[str],
    country_codes: Iterable[str],
    forecast_year: int | None = None,
    forecast_horizon: int | None = None,
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    comparison_options: Mapping[str, object] | None = None,
) -> PredictedComparisonResult:
    resolved_metric_ids = list(metric_ids)
    resolved_country_codes = list(country_codes)
    prediction_result = predict_metric_country_grid(
        canonical_df,
        country_codes=resolved_country_codes,
        metric_ids=resolved_metric_ids,
        horizon_years=horizon_years,
        method=method,
        fallback_method=fallback_method,
    )
    selected_df, selection = _select_predicted_rows(
        prediction_result,
        forecast_year=forecast_year,
        forecast_horizon=forecast_horizon,
        horizon_years=horizon_years,
    )
    comparison_kwargs = dict(comparison_options or {})
    comparison_kwargs.update(
        {
            "metric_ids": resolved_metric_ids,
            "countries_include": resolved_country_codes,
            "year_strategy": selection["comparison_year_strategy"],
            "target_year": selection["comparison_target_year"],
        }
    )
    try:
        comparison_df = compare_countries(selected_df, **comparison_kwargs)
    except MultiComparisonError as exc:
        raise PredictionException(
            PredictionErrorCode.COMPARISON_BRIDGE_FAILED,
            str(exc),
            details={"selection": selection},
        ) from exc
    return PredictedComparisonResult(
        comparison_df=comparison_df,
        prediction_result=prediction_result,
        diagnostics=prediction_result.diagnostics,
        selected_forecast_year=selection["selected_forecast_year"],
        selected_forecast_horizon=selection["selected_forecast_horizon"],
        metadata=selection,
    )


def compare_predicted_profile(
    canonical_df: pd.DataFrame,
    *,
    scoring_config: ScoringConfig,
    profile_name: str,
    country_codes: Iterable[str],
    forecast_year: int | None = None,
    forecast_horizon: int | None = None,
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    comparison_options: Mapping[str, object] | None = None,
) -> PredictedComparisonResult:
    if profile_name not in scoring_config.profiles:
        raise PredictionException(
            PredictionErrorCode.COMPARISON_BRIDGE_FAILED,
            f"unknown scoring profile: {profile_name}",
            details={"profile_name": profile_name},
        )

    resolved_country_codes = list(country_codes)
    prediction_result = predict_metric_country_grid(
        canonical_df,
        country_codes=resolved_country_codes,
        metric_ids=scoring_config.profiles[profile_name].metrics,
        horizon_years=horizon_years,
        method=method,
        fallback_method=fallback_method,
    )
    selected_df, selection = _select_predicted_rows(
        prediction_result,
        forecast_year=forecast_year,
        forecast_horizon=forecast_horizon,
        horizon_years=horizon_years,
    )
    comparison_kwargs = dict(comparison_options or {})
    comparison_kwargs.update(
        {
            "metric_ids": None,
            "countries_include": resolved_country_codes,
            "year_strategy": selection["comparison_year_strategy"],
            "target_year": selection["comparison_target_year"],
            "scoring_config": scoring_config,
            "profile_name": profile_name,
        }
    )
    try:
        comparison_df = compare_countries(selected_df, **comparison_kwargs)
    except MultiComparisonError as exc:
        raise PredictionException(
            PredictionErrorCode.COMPARISON_BRIDGE_FAILED,
            str(exc),
            details={"profile_name": profile_name, "selection": selection},
        ) from exc
    return PredictedComparisonResult(
        comparison_df=comparison_df,
        prediction_result=prediction_result,
        diagnostics=prediction_result.diagnostics,
        selected_forecast_year=selection["selected_forecast_year"],
        selected_forecast_horizon=selection["selected_forecast_horizon"],
        metadata=selection,
    )


def _select_predicted_rows(
    prediction_result: PredictionResult,
    *,
    forecast_year: int | None,
    forecast_horizon: int | None,
    horizon_years: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if forecast_year is not None and forecast_horizon is not None:
        raise PredictionException(
            PredictionErrorCode.INVALID_FORECAST_SELECTION,
            "provide exactly one of forecast_year or forecast_horizon",
            details={
                "forecast_year": forecast_year,
                "forecast_horizon": forecast_horizon,
            },
        )

    working = prediction_result.comparison_ready_df.copy(deep=True)
    if working.empty:
        raise PredictionException(
            PredictionErrorCode.INVALID_FORECAST_SELECTION,
            "no predicted rows are available for comparison",
            details={"prediction_metadata": prediction_result.metadata},
        )
    working = working.loc[
        working[ROW_TYPE_COLUMN].astype("string").eq("predicted")
    ].copy()

    if forecast_year is None and forecast_horizon is None:
        forecast_horizon = int(horizon_years)

    if forecast_year is not None:
        selected_year = int(forecast_year)
        selected = working.loc[
            pd.to_numeric(working[YEAR_COLUMN], errors="coerce").eq(selected_year)
        ].copy()
        if selected.empty:
            available_years = sorted(
                pd.to_numeric(working[YEAR_COLUMN], errors="coerce")
                .dropna()
                .astype(int)
                .unique()
                .tolist()
            )
            raise PredictionException(
                PredictionErrorCode.INVALID_FORECAST_SELECTION,
                f"forecast_year {selected_year} is not present in generated predictions",
                year=selected_year,
                details={
                    "forecast_year": selected_year,
                    "available_years": available_years,
                },
            )
        horizons = sorted(
            pd.to_numeric(selected[FORECAST_HORIZON_COLUMN], errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )
        return selected, {
            "selection_mode": "forecast_year",
            "selected_forecast_year": selected_year,
            "selected_forecast_horizon": horizons[0] if len(horizons) == 1 else None,
            "selected_prediction_years": [selected_year],
            "selected_prediction_horizons": horizons,
            "comparison_year_strategy": YearStrategy.TARGET_YEAR,
            "comparison_target_year": selected_year,
        }

    selected_horizon = int(forecast_horizon)
    selected = working.loc[
        pd.to_numeric(working[FORECAST_HORIZON_COLUMN], errors="coerce").eq(
            selected_horizon
        )
    ].copy()
    if selected.empty:
        available_horizons = sorted(
            pd.to_numeric(working[FORECAST_HORIZON_COLUMN], errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )
        raise PredictionException(
            PredictionErrorCode.INVALID_FORECAST_SELECTION,
            f"forecast_horizon {selected_horizon} is not present in generated predictions",
            details={
                "forecast_horizon": selected_horizon,
                "available_horizons": available_horizons,
            },
        )
    years = sorted(
        pd.to_numeric(selected[YEAR_COLUMN], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    return selected, {
        "selection_mode": "forecast_horizon",
        "selected_forecast_year": years[0] if len(years) == 1 else None,
        "selected_forecast_horizon": selected_horizon,
        "selected_prediction_years": years,
        "selected_prediction_horizons": [selected_horizon],
        "comparison_year_strategy": YearStrategy.LATEST_PER_METRIC,
        "comparison_target_year": None,
    }


__all__ = [
    "compare_predicted_single_metric",
    "compare_predicted_multi_metric",
    "compare_predicted_profile",
]
