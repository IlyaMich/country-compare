from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.config import load_configuration_bundle
from country_compare.config.models import ScoringConfig
from country_compare.data import load_metric_dataframe
from country_compare.data.stores.registry import create_metric_store
from country_compare.prediction import (
    BacktestRequest,
    ForecastOptions,
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    compare_predicted_multi_metric,
    compare_predicted_profile,
    compare_predicted_single_metric,
    predict_metric_country_grid,
    predict_metrics_for_country,
    predict_single_metric,
    predict_single_metric_for_countries,
)
from country_compare.prediction.summaries import (
    build_backtest_result_summary,
    build_predicted_comparison_result_summary,
    build_prediction_result_summary,
    list_available_prediction_methods,
    prediction_exception_to_dict,
)
from country_compare.services.app_context import AppContext
from country_compare.services.dataset_service import DatasetService
from country_compare.services.errors import AppError, error_from_exception
from country_compare.services.results import PredictionServiceResult


class PredictionService:
    """Framework-neutral orchestration for prediction, comparison bridge, and backtesting."""

    def __init__(
        self,
        *,
        context: AppContext,
        dataset_service: DatasetService | None = None,
        config_service: Any | None = None,
    ) -> None:
        self.context = context
        self.dataset_service = dataset_service
        self.config_service = config_service

    def list_prediction_methods(self) -> list[dict[str, Any]]:
        return list_available_prediction_methods()

    def run_single_metric_prediction(
        self,
        *,
        country_code: str,
        metric_id: str,
        horizon_years: int,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        include_actuals: bool = True,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        fail_on_warning: bool = False,
        scenario_id: str = "baseline",
        options: ForecastOptions | None = None,
    ) -> PredictionServiceResult:
        request = SingleMetricPredictionRequest(
            country_code=country_code,
            metric_id=metric_id,
            horizon_years=horizon_years,
            method=method,
            include_actuals=include_actuals,
            history_start_year=history_start_year,
            history_end_year=history_end_year,
            fallback_method=fallback_method,
            fail_on_warning=fail_on_warning,
            scenario_id=scenario_id,
        )
        return self._run_prediction_result(
            mode="single_metric_prediction",
            request=request,
            executor=lambda dataframe: predict_single_metric(
                dataframe,
                request,
                options=options,
            ),
        )

    def run_single_metric_prediction_for_countries(
        self,
        *,
        metric_id: str,
        country_codes: list[str],
        horizon_years: int,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        include_actuals: bool = True,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        fail_fast: bool = False,
        scenario_id: str = "baseline",
        options: ForecastOptions | None = None,
    ) -> PredictionServiceResult:
        request = {
            "metric_id": metric_id,
            "country_codes": list(country_codes),
            "horizon_years": horizon_years,
            "method": method,
            "fallback_method": fallback_method,
            "include_actuals": include_actuals,
            "history_start_year": history_start_year,
            "history_end_year": history_end_year,
            "fail_fast": fail_fast,
            "scenario_id": scenario_id,
        }
        return self._run_prediction_result(
            mode="single_metric_countries_prediction",
            request=request,
            executor=lambda dataframe: predict_single_metric_for_countries(
                dataframe,
                metric_id=metric_id,
                country_codes=country_codes,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                include_actuals=include_actuals,
                history_start_year=history_start_year,
                history_end_year=history_end_year,
                fail_fast=fail_fast,
                scenario_id=scenario_id,
                options=options,
            ),
        )

    def run_metrics_for_country_prediction(
        self,
        *,
        country_code: str,
        metric_ids: list[str],
        horizon_years: int,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        include_actuals: bool = True,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        fail_fast: bool = False,
        scenario_id: str = "baseline",
        options: ForecastOptions | None = None,
    ) -> PredictionServiceResult:
        request = {
            "country_code": country_code,
            "metric_ids": list(metric_ids),
            "horizon_years": horizon_years,
            "method": method,
            "fallback_method": fallback_method,
            "include_actuals": include_actuals,
            "history_start_year": history_start_year,
            "history_end_year": history_end_year,
            "fail_fast": fail_fast,
            "scenario_id": scenario_id,
        }
        return self._run_prediction_result(
            mode="metrics_for_country_prediction",
            request=request,
            executor=lambda dataframe: predict_metrics_for_country(
                dataframe,
                country_code=country_code,
                metric_ids=metric_ids,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                include_actuals=include_actuals,
                history_start_year=history_start_year,
                history_end_year=history_end_year,
                fail_fast=fail_fast,
                scenario_id=scenario_id,
                options=options,
            ),
        )

    def run_metric_country_grid_prediction(
        self,
        *,
        country_codes: list[str],
        metric_ids: list[str],
        horizon_years: int,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        include_actuals: bool = True,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        fail_fast: bool = False,
        scenario_id: str = "baseline",
        options: ForecastOptions | None = None,
    ) -> PredictionServiceResult:
        request = {
            "country_codes": list(country_codes),
            "metric_ids": list(metric_ids),
            "horizon_years": horizon_years,
            "method": method,
            "fallback_method": fallback_method,
            "include_actuals": include_actuals,
            "history_start_year": history_start_year,
            "history_end_year": history_end_year,
            "fail_fast": fail_fast,
            "scenario_id": scenario_id,
        }
        return self._run_prediction_result(
            mode="metric_country_grid_prediction",
            request=request,
            executor=lambda dataframe: predict_metric_country_grid(
                dataframe,
                country_codes=country_codes,
                metric_ids=metric_ids,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                include_actuals=include_actuals,
                history_start_year=history_start_year,
                history_end_year=history_end_year,
                fail_fast=fail_fast,
                scenario_id=scenario_id,
                options=options,
            ),
        )

    def run_predicted_single_metric_comparison(
        self,
        *,
        metric_id: str,
        country_codes: list[str],
        horizon_years: int,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        comparison_options: dict[str, object] | None = None,
    ) -> PredictionServiceResult:
        resolved_comparison_options = self._resolve_predicted_comparison_options(
            comparison_options=comparison_options,
        )
        request = {
            "metric_id": metric_id,
            "country_codes": list(country_codes),
            "horizon_years": horizon_years,
            "forecast_year": forecast_year,
            "forecast_horizon": forecast_horizon,
            "method": method,
            "fallback_method": fallback_method,
            "comparison_options": comparison_options or {},
        }
        return self._run_predicted_comparison_result(
            mode="predicted_single_metric_comparison",
            request=request,
            executor=lambda dataframe: compare_predicted_single_metric(
                dataframe,
                metric_id=metric_id,
                country_codes=country_codes,
                forecast_year=forecast_year,
                forecast_horizon=forecast_horizon,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                comparison_options=resolved_comparison_options,
            ),
        )

    def run_predicted_multi_metric_comparison(
        self,
        *,
        metric_ids: list[str],
        country_codes: list[str],
        horizon_years: int,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        comparison_options: dict[str, object] | None = None,
    ) -> PredictionServiceResult:
        resolved_comparison_options = self._resolve_predicted_comparison_options(
            comparison_options=comparison_options,
        )
        request = {
            "metric_ids": list(metric_ids),
            "country_codes": list(country_codes),
            "horizon_years": horizon_years,
            "forecast_year": forecast_year,
            "forecast_horizon": forecast_horizon,
            "method": method,
            "fallback_method": fallback_method,
            "comparison_options": comparison_options or {},
        }
        return self._run_predicted_comparison_result(
            mode="predicted_multi_metric_comparison",
            request=request,
            executor=lambda dataframe: compare_predicted_multi_metric(
                dataframe,
                metric_ids=metric_ids,
                country_codes=country_codes,
                forecast_year=forecast_year,
                forecast_horizon=forecast_horizon,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                comparison_options=resolved_comparison_options,
            ),
        )

    def run_predicted_profile_comparison(
        self,
        *,
        profile_name: str,
        country_codes: list[str],
        horizon_years: int,
        scoring_config: ScoringConfig | None = None,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: PredictionMethod | str | None = None,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        comparison_options: dict[str, object] | None = None,
    ) -> PredictionServiceResult:
        resolved_scoring_config = scoring_config or self._load_scoring_config()
        resolved_comparison_options = self._resolve_predicted_comparison_options(
            comparison_options=comparison_options,
            scoring_config=resolved_scoring_config,
            profile_name=profile_name,
        )
        request = {
            "profile_name": profile_name,
            "country_codes": list(country_codes),
            "horizon_years": horizon_years,
            "forecast_year": forecast_year,
            "forecast_horizon": forecast_horizon,
            "method": method,
            "fallback_method": fallback_method,
            "comparison_options": comparison_options or {},
        }
        return self._run_predicted_comparison_result(
            mode="predicted_profile_comparison",
            request=request,
            executor=lambda dataframe: compare_predicted_profile(
                dataframe,
                scoring_config=resolved_scoring_config,
                profile_name=profile_name,
                country_codes=country_codes,
                forecast_year=forecast_year,
                forecast_horizon=forecast_horizon,
                horizon_years=horizon_years,
                method=method,
                fallback_method=fallback_method,
                comparison_options=resolved_comparison_options,
            ),
        )

    def run_backtest(
        self,
        *,
        country_code: str,
        metric_id: str,
        method: PredictionMethod | str | None = PredictionMethod.LINEAR_TREND,
        fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
        holdout_years: int = 3,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        scenario_id: str = "baseline",
        options: ForecastOptions | None = None,
    ) -> PredictionServiceResult:
        request = BacktestRequest(
            country_code=country_code,
            metric_id=metric_id,
            holdout_years=holdout_years,
            method=method,
            fallback_method=fallback_method,
            history_start_year=history_start_year,
            history_end_year=history_end_year,
            scenario_id=scenario_id,
        )
        return self._run_backtest_result(
            mode="prediction_backtest",
            request=request,
            executor=lambda dataframe: backtest_series(
                dataframe,
                country_code=country_code,
                metric_id=metric_id,
                method=method,
                fallback_method=fallback_method,
                holdout_years=holdout_years,
                history_start_year=history_start_year,
                history_end_year=history_end_year,
                scenario_id=scenario_id,
                options=options,
            ),
        )

    def translate_prediction_exception(
        self, exc: PredictionException
    ) -> dict[str, Any]:
        return prediction_exception_to_dict(exc)

    def prediction_exception_to_app_error(self, exc: PredictionException) -> AppError:
        payload = prediction_exception_to_dict(exc)
        field_errors: dict[str, str] = {}
        if exc.country_code is not None:
            field_errors["country_code"] = exc.country_code
        if exc.metric_id is not None:
            field_errors["metric_id"] = exc.metric_id
        if exc.year is not None:
            field_errors["year"] = str(exc.year)

        return AppError(
            code=exc.code.value,
            title="Prediction failed",
            user_message=exc.message,
            technical_detail=str(payload),
            field_errors=field_errors,
        )

    def _run_prediction_result(
        self,
        *,
        mode: str,
        request: Any,
        executor: Any,
    ) -> PredictionServiceResult:
        try:
            source_dataframe = self._load_dataframe()
            result = executor(source_dataframe)
            summary = build_prediction_result_summary(result)
            metadata = dict(result.metadata)
            self._attach_dataset_identity(metadata, source_dataframe)
            return PredictionServiceResult(
                mode=mode,
                request=request,
                prediction_result=result,
                dataframe=result.forecast_df.copy(deep=True),
                summary=summary,
                metadata=metadata,
                diagnostics=summary["diagnostics"],
                warnings=list(summary["diagnostics"].get("warnings", [])),
            )
        except Exception as exc:
            return self._error_result(mode=mode, request=request, exc=exc)

    def _run_predicted_comparison_result(
        self,
        *,
        mode: str,
        request: Any,
        executor: Any,
    ) -> PredictionServiceResult:
        try:
            source_dataframe = self._load_dataframe()
            result = executor(source_dataframe)
            summary = build_predicted_comparison_result_summary(result)
            metadata = dict(result.metadata)
            self._attach_dataset_identity(metadata, source_dataframe)
            return PredictionServiceResult(
                mode=mode,
                request=request,
                prediction_result=result.prediction_result,
                predicted_comparison_result=result,
                dataframe=result.comparison_df.copy(deep=True),
                summary=summary,
                metadata=metadata,
                diagnostics=summary["diagnostics"],
                warnings=list(summary["diagnostics"].get("warnings", [])),
            )
        except Exception as exc:
            return self._error_result(mode=mode, request=request, exc=exc)

    def _run_backtest_result(
        self,
        *,
        mode: str,
        request: Any,
        executor: Any,
    ) -> PredictionServiceResult:
        try:
            source_dataframe = self._load_dataframe()
            result = executor(source_dataframe)
            summary = build_backtest_result_summary(result)
            metadata = dict(result.metadata)
            self._attach_dataset_identity(metadata, source_dataframe)
            return PredictionServiceResult(
                mode=mode,
                request=request,
                backtest_result=result,
                dataframe=result.actual_vs_predicted_df.copy(deep=True),
                summary=summary,
                metadata=metadata,
                diagnostics=summary["diagnostics"],
                warnings=list(summary["diagnostics"].get("warnings", [])),
            )
        except Exception as exc:
            return self._error_result(mode=mode, request=request, exc=exc)

    def _attach_dataset_identity(
        self, metadata: dict[str, Any], dataframe: pd.DataFrame
    ) -> None:
        if self.dataset_service is None or "dataset" in metadata:
            return
        identity_getter = getattr(self.dataset_service, "get_dataset_identity", None)
        if identity_getter is None:
            return
        try:
            identity = identity_getter(dataframe)
        except Exception:
            return
        if identity:
            metadata["dataset"] = identity

    def _error_result(
        self,
        *,
        mode: str,
        request: Any,
        exc: Exception,
    ) -> PredictionServiceResult:
        if isinstance(exc, PredictionException):
            error = self.prediction_exception_to_app_error(exc)
        else:
            error = error_from_exception(
                exc,
                default_title="Unexpected prediction error",
                default_user_message="The prediction request could not be completed.",
            )

        return PredictionServiceResult(
            mode=mode,
            request=request,
            error=error,
            diagnostics={
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
        )

    def _load_dataframe(self) -> pd.DataFrame:
        if self.dataset_service is not None and hasattr(
            self.dataset_service, "load_dataframe"
        ):
            return self.dataset_service.load_dataframe()

        store = self._create_store_from_context()
        return load_metric_dataframe(store=store)

    def _resolve_predicted_comparison_options(
        self,
        comparison_options: dict[str, object] | None = None,
        *,
        scoring_config: ScoringConfig | None = None,
        profile_name: str | None = None,
    ) -> dict[str, object]:
        bundle = self._load_configuration_bundle()
        resolved_options = dict(comparison_options or {})
        resolved_options.setdefault("metrics_config", bundle.metrics)
        resolved_options.setdefault("scoring_config", scoring_config or bundle.scoring)
        if profile_name is not None:
            resolved_options.setdefault("profile_name", profile_name)
        return resolved_options

    def _load_configuration_bundle(self) -> Any:
        if self.config_service is not None and hasattr(
            self.config_service, "load_bundle"
        ):
            return self.config_service.load_bundle()

        return load_configuration_bundle(
            self.context.metrics_config_path,
            self.context.scoring_config_path,
            validate=True,
        )

    def _load_scoring_config(self) -> ScoringConfig:
        return self._load_configuration_bundle().scoring

    def _create_store_from_context(self) -> Any:
        kwargs: dict[str, Any] = {}
        store_path = getattr(self.context, "store_path", None)
        if store_path:
            kwargs["path"] = Path(store_path)
        backend = getattr(self.context, "store_backend", "parquet")
        return create_metric_store(backend=backend, **kwargs)
