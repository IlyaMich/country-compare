from __future__ import annotations

from typing import Any

from country_compare.config.models import YearStrategy
from country_compare.services import AppContext, AppFacade
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.config_service import ConfigService
from country_compare.services.dataset_service import DatasetService
from country_compare.services.prediction_service import PredictionService
from country_compare.services.presentation_service import PresentationService
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)


class LocalCountryCompareClient:
    """Country Compare client backed by in-process services."""

    mode = "local"

    def __init__(
        self,
        *,
        context: AppContext,
        facade: AppFacade | None = None,
        services: dict[str, Any] | None = None,
    ) -> None:
        self.context = context
        self.facade = facade or AppFacade(context)
        self._services_override = services
        self._services_cache: dict[str, Any] | None = None

    def as_ui_services(self) -> dict[str, object]:
        return dict(self._services())

    def get_dataset_summary(self) -> Any:
        return self._services()["dataset_service"].get_dataset_summary()

    def get_overview_status(
        self, *, validate_config_against_dataset: bool = False
    ) -> Any:
        return self.facade.get_overview_status(
            validate_config_against_dataset=validate_config_against_dataset,
        )

    def list_countries(self) -> list[Any]:
        dataset = self._services()["dataset_service"]
        if hasattr(dataset, "get_country_catalog"):
            return list(dataset.get_country_catalog())
        return list(dataset.list_countries())

    def list_metrics(self) -> list[Any]:
        dataset = self._services()["dataset_service"]
        if hasattr(dataset, "get_metric_catalog"):
            return list(dataset.get_metric_catalog())
        return list(dataset.list_metrics())

    def list_years(self) -> list[int]:
        return list(self._services()["dataset_service"].list_years())

    def list_profiles(self) -> list[Any]:
        return list(self._services()["config_service"].get_profile_summaries())

    def list_prediction_methods(self) -> list[dict[str, Any]]:
        return list(self._services()["prediction_service"].list_prediction_methods())

    def run_single_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_id: str,
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        request = SingleMetricRequest(
            countries=country_codes,
            metric_id=metric_id,
            year_strategy=year_strategy,
            target_year=target_year,
            top_n=top_n,
        )
        result = self._services()["comparison_service"].run_single_metric(request)
        if result.ok:
            return self._services()[
                "presentation_service"
            ].build_single_metric_presentation(result)
        return result

    def run_multi_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_ids: list[str],
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        request = MultiMetricRequest(
            countries=country_codes,
            metric_ids=metric_ids,
            year_strategy=year_strategy,
            target_year=target_year,
            top_n=top_n,
        )
        result = self._services()["comparison_service"].run_multi_metric(request)
        if result.ok:
            return self._services()[
                "presentation_service"
            ].build_multi_metric_presentation(result)
        return result

    def run_weighted_score(
        self,
        *,
        country_codes: list[str],
        profile_name: str,
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        request = WeightedScoreRequest(
            countries=country_codes,
            profile_name=profile_name,
            year_strategy=year_strategy,
            target_year=target_year,
            top_n=top_n,
        )
        result = self._services()["comparison_service"].run_weighted_score(request)
        if result.ok:
            return self._services()[
                "presentation_service"
            ].build_weighted_score_presentation(result)
        return result

    def run_single_metric_prediction(
        self,
        *,
        country_code: str,
        metric_id: str,
        horizon_years: int,
        method: str | None = None,
        fallback_method: str | None = "last_observed",
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        scenario_id: str = "baseline",
    ) -> Any:
        return self._services()["prediction_service"].run_single_metric_prediction(
            country_code=country_code,
            metric_id=metric_id,
            horizon_years=horizon_years,
            method=method,
            fallback_method=fallback_method,
            history_start_year=history_start_year,
            history_end_year=history_end_year,
            scenario_id=scenario_id,
        )

    def run_single_metric_prediction_for_countries(
        self,
        *,
        metric_id: str,
        country_codes: list[str],
        horizon_years: int,
        method: str | None = None,
        fallback_method: str | None = "last_observed",
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        fail_fast: bool = False,
        scenario_id: str = "baseline",
    ) -> Any:
        return self._services()[
            "prediction_service"
        ].run_single_metric_prediction_for_countries(
            metric_id=metric_id,
            country_codes=country_codes,
            horizon_years=horizon_years,
            method=method,
            fallback_method=fallback_method,
            history_start_year=history_start_year,
            history_end_year=history_end_year,
            fail_fast=fail_fast,
            scenario_id=scenario_id,
        )

    def run_predicted_single_metric_comparison(
        self,
        *,
        metric_id: str,
        country_codes: list[str],
        horizon_years: int,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: str | None = None,
        fallback_method: str | None = "last_observed",
        comparison_options: dict[str, object] | None = None,
    ) -> Any:
        return self._services()[
            "prediction_service"
        ].run_predicted_single_metric_comparison(
            metric_id=metric_id,
            country_codes=country_codes,
            horizon_years=horizon_years,
            forecast_year=forecast_year,
            forecast_horizon=forecast_horizon,
            method=method,
            fallback_method=fallback_method,
            comparison_options=comparison_options,
        )

    def run_predicted_multi_metric_comparison(
        self,
        *,
        metric_ids: list[str],
        country_codes: list[str],
        horizon_years: int,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: str | None = None,
        fallback_method: str | None = "last_observed",
        comparison_options: dict[str, object] | None = None,
    ) -> Any:
        return self._services()[
            "prediction_service"
        ].run_predicted_multi_metric_comparison(
            metric_ids=metric_ids,
            country_codes=country_codes,
            horizon_years=horizon_years,
            forecast_year=forecast_year,
            forecast_horizon=forecast_horizon,
            method=method,
            fallback_method=fallback_method,
            comparison_options=comparison_options,
        )

    def run_predicted_profile_comparison(
        self,
        *,
        profile_name: str,
        country_codes: list[str],
        horizon_years: int,
        forecast_year: int | None = None,
        forecast_horizon: int | None = None,
        method: str | None = None,
        fallback_method: str | None = "last_observed",
        comparison_options: dict[str, object] | None = None,
    ) -> Any:
        return self._services()["prediction_service"].run_predicted_profile_comparison(
            profile_name=profile_name,
            country_codes=country_codes,
            horizon_years=horizon_years,
            forecast_year=forecast_year,
            forecast_horizon=forecast_horizon,
            method=method,
            fallback_method=fallback_method,
            comparison_options=comparison_options,
        )

    def run_backtest(
        self,
        *,
        country_code: str,
        metric_id: str,
        method: str | None = "linear_trend",
        fallback_method: str | None = "last_observed",
        holdout_years: int = 2,
        history_start_year: int | None = None,
        history_end_year: int | None = None,
        scenario_id: str = "baseline",
    ) -> Any:
        return self._services()["prediction_service"].run_backtest(
            country_code=country_code,
            metric_id=metric_id,
            method=method,
            fallback_method=fallback_method,
            holdout_years=holdout_years,
            history_start_year=history_start_year,
            history_end_year=history_end_year,
            scenario_id=scenario_id,
        )

    def _services(self) -> dict[str, Any]:
        if self._services_override is not None:
            return self._services_override

        if self._services_cache is None:
            dataset_service = DatasetService(context=self.context)
            config_service = ConfigService(
                context=self.context,
                dataset_service=dataset_service,
            )
            comparison_service = ComparisonService(
                context=self.context,
                dataset_service=dataset_service,
                config_service=config_service,
            )
            prediction_service = PredictionService(
                context=self.context,
                dataset_service=dataset_service,
                config_service=config_service,
            )
            self._services_cache = {
                "context": self.context,
                "dataset_service": dataset_service,
                "config_service": config_service,
                "comparison_service": comparison_service,
                "prediction_service": prediction_service,
                "presentation_service": PresentationService(),
            }

        return self._services_cache
