from __future__ import annotations

from typing import Any, Protocol

from country_compare.config.models import YearStrategy


class CountryCompareClient(Protocol):
    """UI-facing client boundary for local and HTTP-backed operation."""

    @property
    def mode(self) -> str:
        """Return the client mode: local or http."""

    def get_dataset_summary(self) -> Any:
        """Return dataset summary metadata."""

    def get_overview_status(
        self, *, validate_config_against_dataset: bool = False
    ) -> Any:
        """Return overview/readiness-style status for the UI."""

    def list_countries(self) -> list[Any]:
        """Return country selector options."""

    def list_metrics(self) -> list[Any]:
        """Return metric selector options."""

    def list_years(self) -> list[int]:
        """Return available dataset years."""

    def list_profiles(self) -> list[Any]:
        """Return scoring profile selector options."""

    def list_prediction_methods(self) -> list[dict[str, Any]]:
        """Return available prediction methods."""

    def run_single_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_id: str,
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        """Run a single-metric comparison and return a UI-renderable result."""

    def run_multi_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_ids: list[str],
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        """Run a multi-metric comparison and return a UI-renderable result."""

    def run_weighted_score(
        self,
        *,
        country_codes: list[str],
        profile_name: str,
        year_strategy: YearStrategy | str,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> Any:
        """Run a profile scoring comparison and return a UI-renderable result."""

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
        """Run a single-country, single-metric forecast."""

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
        """Run a multi-country, single-metric forecast."""

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
        """Run a forecast-based single-metric comparison."""

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
        """Run a forecast-based multi-metric comparison."""

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
        """Run a forecast-based profile comparison."""

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
        """Run a prediction backtest."""
