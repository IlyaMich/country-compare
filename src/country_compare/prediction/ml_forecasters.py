from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.contract import VALUE_COLUMN, YEAR_COLUMN
from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.forecasters import BaseForecaster
from country_compare.prediction.models import (
    ForecastContext,
    ForecastOptions,
    ForecastPoint,
    RawForecastResult,
)

try:
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
except ImportError:  # pragma: no cover - exercised by non-ML installs
    ElasticNet = None
    make_pipeline = None
    StandardScaler = None


def is_elasticnet_available() -> bool:
    return (
        ElasticNet is not None
        and make_pipeline is not None
        and StandardScaler is not None
    )


class ElasticNetTrendForecaster(BaseForecaster):
    method_id = "elasticnet_trend"
    display_name = "ElasticNet trend"
    description = (
        "Fits a regularized trend model using year-offset and "
        "squared year-offset features."
    )

    minimum_observations = 8
    minimum_distinct_years = 4
    default_alpha = 0.1
    default_l1_ratio = 0.5
    default_max_iter = 10_000

    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []

        if not is_elasticnet_available():
            reasons.append(
                "elasticnet_trend requires scikit-learn; install with the 'ml' extra"
            )

        years = pd.to_numeric(series[YEAR_COLUMN], errors="coerce").dropna()
        values = pd.to_numeric(series[VALUE_COLUMN], errors="coerce").dropna()

        if len(series.index) < self.minimum_observations:
            reasons.append(
                f"elasticnet_trend requires at least {self.minimum_observations} observations"
            )

        if years.nunique() < self.minimum_distinct_years:
            reasons.append(
                "elasticnet_trend requires at least "
                f"{self.minimum_distinct_years} distinct years"
            )

        if len(years.index) < len(series.index):
            reasons.append(
                "elasticnet_trend requires numeric years for every observation"
            )

        if len(values.index) < len(series.index):
            reasons.append(
                "elasticnet_trend requires numeric values for every observation"
            )

        return len(reasons) == 0, reasons

    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        self._require_supported(series, context=context, options=options)

        elastic_net_cls = ElasticNet
        make_pipeline_fn = make_pipeline
        standard_scaler_cls = StandardScaler

        if (
            elastic_net_cls is None
            or make_pipeline_fn is None
            or standard_scaler_cls is None
        ):
            raise PredictionException(
                PredictionErrorCode.UNSUPPORTED_METHOD,
                "elasticnet_trend requires scikit-learn; install with the 'ml' extra",
                country_code=context.country_code,
                metric_id=context.metric_id,
                details={
                    "method": self.method_id,
                    "missing_dependency": "scikit-learn",
                },
            )

        sorted_series = series.copy(deep=True)
        sorted_series[YEAR_COLUMN] = pd.to_numeric(
            sorted_series[YEAR_COLUMN], errors="coerce"
        ).astype("int64")
        sorted_series[VALUE_COLUMN] = pd.to_numeric(
            sorted_series[VALUE_COLUMN], errors="coerce"
        ).astype("float64")
        sorted_series = sorted_series.sort_values(by=YEAR_COLUMN, kind="mergesort")

        training_years = [int(year) for year in sorted_series[YEAR_COLUMN].tolist()]
        training_values = [
            float(value) for value in sorted_series[VALUE_COLUMN].tolist()
        ]
        origin_year = min(training_years)

        x_train = _build_feature_matrix(training_years, origin_year=origin_year)
        x_future = _build_feature_matrix(
            [int(year) for year in future_years], origin_year=origin_year
        )

        model: Any = make_pipeline_fn(
            standard_scaler_cls(),
            elastic_net_cls(
                alpha=self.default_alpha,
                l1_ratio=self.default_l1_ratio,
                max_iter=self.default_max_iter,
            ),
        )
        model.fit(x_train, training_values)

        predicted_values = [float(value) for value in model.predict(x_future)]

        points = [
            ForecastPoint(year=int(year), value=value, horizon=index + 1)
            for index, (year, value) in enumerate(
                zip(future_years, predicted_values, strict=True)
            )
        ]

        elasticnet_step: Any = model.named_steps["elasticnet"]
        metadata = {
            "alpha": self.default_alpha,
            "l1_ratio": self.default_l1_ratio,
            "max_iter": self.default_max_iter,
            "feature_columns": ["year_offset", "year_offset_squared"],
            "origin_year": origin_year,
            "training_observation_count": len(training_years),
            "training_start_year": min(training_years),
            "training_end_year": max(training_years),
            "elasticnet_coefficients_scaled_features": [
                float(coef) for coef in elasticnet_step.coef_
            ],
            "elasticnet_intercept_scaled_features": float(elasticnet_step.intercept_),
        }

        warnings: list[str] = []
        if context.missing_years:
            warnings.append(
                "elasticnet_trend fit the available observations despite gaps in the "
                "training years"
            )

        return RawForecastResult(
            method_id=self.method_id,
            points=points,
            forecaster_info=self.info(metadata=metadata),
            diagnostics_metadata=metadata,
            warnings=warnings,
        )


def _build_feature_matrix(years: list[int], *, origin_year: int) -> list[list[float]]:
    return [
        [
            float(year - origin_year),
            float((year - origin_year) ** 2),
        ]
        for year in years
    ]
