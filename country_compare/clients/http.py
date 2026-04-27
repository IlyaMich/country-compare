from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import pandas as pd

from country_compare.clients.errors import (
    ClientBackendError,
    ClientConnectionError,
    ClientResponseError,
)
from country_compare.prediction.summaries import list_available_prediction_methods
from country_compare.services.errors import AppError
from country_compare.services.models import (
    CategorySummary,
    ConfigStatus,
    CountryOption,
    DatasetSummary,
    MetricOption,
    OverviewStatus,
    ProfileOption,
    ValidationReport,
)
from country_compare.services.results import (
    ComparisonResult,
    PredictionServiceResult,
    PresentationResult,
)


class _HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class _SyncHttpClient(Protocol):
    def get(self, url: str) -> _HttpResponse: ...

    def post(self, url: str, *, json: Any) -> _HttpResponse: ...


@dataclass(slots=True)
class _HttpComparisonResult(ComparisonResult):
    presentation: PresentationResult | None = None


class HttpCountryCompareClient:
    """Country Compare client backed by the FastAPI HTTP API."""

    mode = "http"

    def __init__(
        self,
        api_url: str,
        *,
        http_client: _SyncHttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        normalized_url = api_url.rstrip("/")
        if not normalized_url:
            raise ValueError("api_url must not be empty")

        self.api_url = normalized_url
        self._owns_http_client = http_client is None
        self._http_client: _SyncHttpClient = http_client or httpx.Client(
            base_url=self.api_url,
            timeout=timeout,
        )

    def close(self) -> None:
        if self._owns_http_client and hasattr(self._http_client, "close"):
            self._http_client.close()  # type: ignore[attr-defined]

    def as_ui_services(self) -> dict[str, object]:
        return {
            "context": None,
            "dataset_service": _HttpDatasetServiceAdapter(self),
            "config_service": _HttpConfigServiceAdapter(self),
            "comparison_service": _HttpComparisonServiceAdapter(self),
            "prediction_service": _HttpPredictionServiceAdapter(self),
            "presentation_service": _HttpPresentationServiceAdapter(),
        }

    def get_dataset_summary(self) -> DatasetSummary:
        payload = self._get_json("/api/v1/metadata/dataset")
        return _dataset_summary_from_payload(payload)

    def get_overview_status(
        self, *, validate_config_against_dataset: bool = False
    ) -> OverviewStatus:
        dataset = self.get_dataset_summary()
        profiles = self.list_profiles()
        metrics = self.list_metrics()
        ready_payload: dict[str, Any] = {}

        if validate_config_against_dataset:
            try:
                ready_payload = self._get_json("/ready")
            except ClientBackendError as exc:
                ready_payload = {
                    "status": "not_ready",
                    "error": {
                        "code": exc.error.code,
                        "title": exc.error.title,
                        "user_message": exc.error.user_message,
                        "technical_detail": exc.error.technical_detail,
                    },
                }

        config_error = _app_error_from_payload(ready_payload.get("error"))
        valid = ready_payload.get("status") != "not_ready" and config_error is None

        config = ConfigStatus(
            metrics_config_path="(remote backend)",
            scoring_config_path="(remote backend)",
            metrics_config_exists=True,
            scoring_config_exists=True,
            metrics_count=len(metrics),
            profile_count=len(profiles),
            default_profile=None,
            profiles=tuple(profiles),
            bundle_loaded=valid,
            validation=ValidationReport(
                valid=valid,
                messages=(
                    ("Remote backend readiness check passed.",)
                    if valid
                    else ("Remote backend readiness check failed.",)
                ),
                error=config_error,
            ),
            error=config_error,
        )

        warnings = tuple(str(item) for item in ready_payload.get("warnings", []) or ())
        return OverviewStatus(dataset=dataset, config=config, warnings=warnings)

    def list_countries(self) -> list[CountryOption]:
        payload = self._get_json("/api/v1/metadata/countries")
        return [
            CountryOption(
                code=str(item.get("code") or item.get("country_code") or "").upper(),
                name=str(item.get("name") or item.get("country_name") or ""),
            )
            for item in payload.get("countries", []) or []
        ]

    def list_metrics(self) -> list[MetricOption]:
        payload = self._get_json("/api/v1/metadata/metrics")
        return [
            MetricOption(
                metric_id=str(item.get("metric_id") or item.get("id") or ""),
                display_name=str(
                    item.get("display_name")
                    or item.get("metric_name")
                    or item.get("metric_id")
                    or ""
                ),
                category=item.get("category"),
                unit=item.get("unit"),
            )
            for item in payload.get("metrics", []) or []
        ]

    def list_years(self) -> list[int]:
        payload = self._get_json("/api/v1/metadata/years")
        return [int(year) for year in payload.get("years", []) or []]

    def list_profiles(self) -> list[ProfileOption]:
        payload = self._get_json("/api/v1/metadata/profiles")
        profiles: list[ProfileOption] = []

        for item in payload.get("profiles", []) or []:
            name = str(item.get("name") or item.get("profile_name") or "").strip()
            metric_ids = item.get("metric_ids") or item.get("metrics") or []
            metric_count = item.get("metric_count")
            profiles.append(
                ProfileOption(
                    name=name,
                    metric_count=int(
                        metric_count if metric_count is not None else len(metric_ids)
                    ),
                    description=item.get("description"),
                    year_strategy=item.get("year_strategy"),
                    missing_data_policy=item.get("missing_data_policy"),
                )
            )

        return profiles

    def list_prediction_methods(self) -> list[dict[str, Any]]:
        # No API metadata endpoint exists for prediction methods in Phase 6.
        # Keep this local registry lookup so HTTP mode can populate the selector
        # without adding a new backend route.
        return list_available_prediction_methods()

    def run_single_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_id: str,
        year_strategy: Any,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> PresentationResult:
        payload = self._post_json(
            "/api/v1/compare/single-metric",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "metric_id": metric_id,
                    "year_strategy": _enum_value(year_strategy),
                    "target_year": target_year,
                    "top_n": top_n,
                }
            ),
        )
        return _presentation_from_envelope(payload, fallback_mode="single_metric")

    def run_multi_metric_comparison(
        self,
        *,
        country_codes: list[str],
        metric_ids: list[str],
        year_strategy: Any,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> PresentationResult:
        payload = self._post_json(
            "/api/v1/compare/multi-metric",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "metric_ids": list(metric_ids),
                    "year_strategy": _enum_value(year_strategy),
                    "target_year": target_year,
                    "top_n": top_n,
                }
            ),
        )
        return _presentation_from_envelope(payload, fallback_mode="multi_metric")

    def run_weighted_score(
        self,
        *,
        country_codes: list[str],
        profile_name: str,
        year_strategy: Any,
        target_year: int | None = None,
        top_n: int | None = None,
    ) -> PresentationResult:
        payload = self._post_json(
            "/api/v1/score/profile",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "profile_name": profile_name,
                    "year_strategy": _enum_value(year_strategy),
                    "target_year": target_year,
                    "top_n": top_n,
                }
            ),
        )
        return _presentation_from_envelope(payload, fallback_mode="weighted_score")

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
    ) -> PredictionServiceResult:
        primary_payload = _drop_none(
            {
                "country_codes": [country_code],
                "metric_id": metric_id,
                "horizon_years": int(horizon_years),
                "method": method,
                "fallback_method": fallback_method,
                "history_start_year": history_start_year,
                "history_end_year": history_end_year,
                "scenario_id": scenario_id,
            }
        )
        fallback_payload = dict(primary_payload)
        fallback_payload["country_code"] = country_code
        fallback_payload.pop("country_codes", None)

        payload = self._post_json(
            "/api/v1/prediction/single-metric",
            primary_payload,
            fallback_json=fallback_payload,
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="single_metric_prediction",
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
    ) -> PredictionServiceResult:
        payload = self._post_json(
            "/api/v1/prediction/single-metric",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "metric_id": metric_id,
                    "horizon_years": int(horizon_years),
                    "method": method,
                    "fallback_method": fallback_method,
                    "history_start_year": history_start_year,
                    "history_end_year": history_end_year,
                    "fail_fast": fail_fast,
                    "scenario_id": scenario_id,
                }
            ),
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="single_metric_countries_prediction",
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
    ) -> PredictionServiceResult:
        payload = self._post_json(
            "/api/v1/prediction/compare/single-metric",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "metric_id": metric_id,
                    "horizon_years": int(horizon_years),
                    "forecast_year": forecast_year,
                    "forecast_horizon": forecast_horizon,
                    "method": method,
                    "fallback_method": fallback_method,
                    "comparison_options": comparison_options or {},
                }
            ),
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="predicted_single_metric_comparison",
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
    ) -> PredictionServiceResult:
        payload = self._post_json(
            "/api/v1/prediction/compare/multi-metric",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "metric_ids": list(metric_ids),
                    "horizon_years": int(horizon_years),
                    "forecast_year": forecast_year,
                    "forecast_horizon": forecast_horizon,
                    "method": method,
                    "fallback_method": fallback_method,
                    "comparison_options": comparison_options or {},
                }
            ),
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="predicted_multi_metric_comparison",
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
    ) -> PredictionServiceResult:
        payload = self._post_json(
            "/api/v1/prediction/compare/profile",
            _drop_none(
                {
                    "country_codes": list(country_codes),
                    "profile_name": profile_name,
                    "horizon_years": int(horizon_years),
                    "forecast_year": forecast_year,
                    "forecast_horizon": forecast_horizon,
                    "method": method,
                    "fallback_method": fallback_method,
                    "comparison_options": comparison_options or {},
                }
            ),
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="predicted_profile_comparison",
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
    ) -> PredictionServiceResult:
        primary_payload = _drop_none(
            {
                "country_codes": [country_code],
                "metric_id": metric_id,
                "method": method,
                "fallback_method": fallback_method,
                "holdout_years": int(holdout_years),
                "history_start_year": history_start_year,
                "history_end_year": history_end_year,
                "scenario_id": scenario_id,
            }
        )
        fallback_payload = dict(primary_payload)
        fallback_payload["country_code"] = country_code
        fallback_payload.pop("country_codes", None)

        payload = self._post_json(
            "/api/v1/prediction/backtest",
            primary_payload,
            fallback_json=fallback_payload,
        )
        return _prediction_result_from_envelope(
            payload,
            fallback_mode="prediction_backtest",
        )

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            response = self._http_client.get(path)
        except httpx.RequestError as exc:
            raise ClientConnectionError(str(exc)) from exc
        return self._decode_response(response)

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        fallback_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http_client.post(path, json=payload)
        except httpx.RequestError as exc:
            raise ClientConnectionError(str(exc)) from exc

        if response.status_code == 422 and fallback_json is not None:
            try:
                response = self._http_client.post(path, json=fallback_json)
            except httpx.RequestError as exc:
                raise ClientConnectionError(str(exc)) from exc

        return self._decode_response(response)

    def _decode_response(self, response: _HttpResponse) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ClientResponseError(
                "Response body was not valid JSON.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(payload, dict):
            raise ClientResponseError(
                f"Expected JSON object response, got {type(payload).__name__}.",
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            error = _app_error_from_payload(payload.get("error") or payload)
            if error is None:
                error = AppError(
                    code="backend_error",
                    title="Backend error",
                    user_message="The backend could not complete the request.",
                )

            raise ClientBackendError(
                error,
                status_code=response.status_code,
            )

        return payload


class _HttpDatasetServiceAdapter:
    def __init__(self, client: HttpCountryCompareClient) -> None:
        self.client = client

    def get_dataset_summary(self) -> DatasetSummary:
        return self.client.get_dataset_summary()

    def list_countries(self) -> tuple[CountryOption, ...]:
        return tuple(self.client.list_countries())

    def get_country_catalog(self) -> tuple[CountryOption, ...]:
        return self.list_countries()

    def list_metrics(self) -> tuple[MetricOption, ...]:
        return tuple(self.client.list_metrics())

    def get_metric_catalog(self) -> tuple[MetricOption, ...]:
        return self.list_metrics()

    def list_years(self) -> tuple[int, ...]:
        return tuple(self.client.list_years())


class _HttpConfigServiceAdapter:
    def __init__(self, client: HttpCountryCompareClient) -> None:
        self.client = client

    def get_profile_summaries(self) -> tuple[ProfileOption, ...]:
        return tuple(self.client.list_profiles())


class _HttpComparisonServiceAdapter:
    def __init__(self, client: HttpCountryCompareClient) -> None:
        self.client = client

    def run_single_metric(self, request: Any) -> ComparisonResult:
        presentation = self.client.run_single_metric_comparison(
            country_codes=list(request.countries),
            metric_id=str(request.metric_id),
            year_strategy=request.year_strategy,
            target_year=request.target_year,
            top_n=request.top_n,
        )
        return _comparison_result_from_presentation(presentation, request=request)

    def run_multi_metric(self, request: Any) -> ComparisonResult:
        presentation = self.client.run_multi_metric_comparison(
            country_codes=list(request.countries),
            metric_ids=list(request.metric_ids),
            year_strategy=request.year_strategy,
            target_year=request.target_year,
            top_n=request.top_n,
        )
        return _comparison_result_from_presentation(presentation, request=request)

    def run_weighted_score(self, request: Any) -> ComparisonResult:
        presentation = self.client.run_weighted_score(
            country_codes=list(request.countries),
            profile_name=str(request.profile_name),
            year_strategy=request.year_strategy,
            target_year=request.target_year,
            top_n=request.top_n,
        )
        return _comparison_result_from_presentation(presentation, request=request)


class _HttpPredictionServiceAdapter:
    def __init__(self, client: HttpCountryCompareClient) -> None:
        self.client = client

    def list_prediction_methods(self) -> list[dict[str, Any]]:
        return self.client.list_prediction_methods()

    def run_single_metric_prediction(self, **kwargs: Any) -> PredictionServiceResult:
        return self.client.run_single_metric_prediction(**kwargs)

    def run_single_metric_prediction_for_countries(
        self, **kwargs: Any
    ) -> PredictionServiceResult:
        return self.client.run_single_metric_prediction_for_countries(**kwargs)

    def run_predicted_single_metric_comparison(
        self, **kwargs: Any
    ) -> PredictionServiceResult:
        return self.client.run_predicted_single_metric_comparison(**kwargs)

    def run_predicted_multi_metric_comparison(
        self, **kwargs: Any
    ) -> PredictionServiceResult:
        return self.client.run_predicted_multi_metric_comparison(**kwargs)

    def run_predicted_profile_comparison(
        self, **kwargs: Any
    ) -> PredictionServiceResult:
        return self.client.run_predicted_profile_comparison(**kwargs)

    def run_backtest(self, **kwargs: Any) -> PredictionServiceResult:
        return self.client.run_backtest(**kwargs)


class _HttpPresentationServiceAdapter:
    def build_single_metric_presentation(
        self, result: ComparisonResult
    ) -> PresentationResult:
        return _presentation_from_comparison_result(
            result, fallback_mode="single_metric"
        )

    def build_multi_metric_presentation(
        self, result: ComparisonResult
    ) -> PresentationResult:
        return _presentation_from_comparison_result(
            result, fallback_mode="multi_metric"
        )

    def build_weighted_score_presentation(
        self, result: ComparisonResult
    ) -> PresentationResult:
        return _presentation_from_comparison_result(
            result, fallback_mode="weighted_score"
        )


def _presentation_from_comparison_result(
    result: ComparisonResult,
    *,
    fallback_mode: str,
) -> PresentationResult:
    if isinstance(result, _HttpComparisonResult) and result.presentation is not None:
        return result.presentation

    return PresentationResult(
        mode=getattr(result, "mode", fallback_mode) or fallback_mode,
        request=getattr(result, "request", None),
        table=getattr(result, "dataframe", None),
        metadata=getattr(result, "metadata", {}) or {},
        diagnostics=getattr(result, "diagnostics", {}) or {},
        warnings=list(getattr(result, "warnings", []) or []),
        error=getattr(result, "error", None),
    )


def _comparison_result_from_presentation(
    presentation: PresentationResult,
    *,
    request: Any,
) -> ComparisonResult:
    table = presentation.table or _first_dataframe(presentation.tables)
    return _HttpComparisonResult(
        mode=presentation.mode,
        request=request,
        dataframe=table,
        metadata=presentation.metadata,
        diagnostics=presentation.diagnostics,
        warnings=presentation.warnings,
        error=presentation.error,
        presentation=presentation,
    )


def _presentation_from_envelope(
    payload: Mapping[str, Any],
    *,
    fallback_mode: str,
) -> PresentationResult:
    error = _app_error_from_payload(payload.get("error"))
    tables = _tables_from_payload(payload.get("tables"))
    table = _first_dataframe(tables)

    return PresentationResult(
        mode=str(payload.get("mode") or fallback_mode),
        request=payload.get("request"),
        summary=dict(payload.get("summary") or {}),
        table=table,
        tables=tables,
        metadata=dict(payload.get("metadata") or {}),
        diagnostics=dict(payload.get("diagnostics") or {}),
        warnings=[str(item) for item in payload.get("warnings", []) or []],
        messages=[],
        error=error,
    )


def _prediction_result_from_envelope(
    payload: Mapping[str, Any],
    *,
    fallback_mode: str,
) -> PredictionServiceResult:
    error = _app_error_from_payload(payload.get("error"))
    tables = _tables_from_payload(payload.get("tables"))
    dataframe = _first_dataframe(tables)

    return PredictionServiceResult(
        mode=str(payload.get("mode") or fallback_mode),
        request=payload.get("request"),
        dataframe=dataframe,
        summary=dict(payload.get("summary") or {}),
        metadata=dict(payload.get("metadata") or {}),
        diagnostics=dict(payload.get("diagnostics") or {}),
        warnings=[str(item) for item in payload.get("warnings", []) or []],
        error=error,
    )


def _dataset_summary_from_payload(payload: Mapping[str, Any]) -> DatasetSummary:
    categories = tuple(
        CategorySummary(
            name=str(item.get("name") or item.get("category") or ""),
            row_count=int(item.get("row_count") or item.get("rows") or 0),
            country_count=int(item.get("country_count") or item.get("countries") or 0),
            metric_count=int(item.get("metric_count") or item.get("metrics") or 0),
        )
        for item in payload.get("categories", []) or []
    )

    return DatasetSummary(
        exists=bool(payload.get("exists", False)),
        backend=str(payload.get("backend") or ""),
        dataset_path=payload.get("dataset_path"),
        row_count=int(payload.get("row_count") or 0),
        country_count=int(payload.get("country_count") or 0),
        metric_count=int(payload.get("metric_count") or 0),
        year_min=payload.get("year_min"),
        year_max=payload.get("year_max"),
        available_columns=tuple(
            str(item) for item in payload.get("available_columns", []) or []
        ),
        categories=categories,
        error=_app_error_from_payload(payload.get("error")),
    )


def _tables_from_payload(value: Any) -> dict[str, pd.DataFrame]:
    if not isinstance(value, Mapping):
        return {}

    tables: dict[str, pd.DataFrame] = {}
    for name, table_payload in value.items():
        dataframe = _dataframe_from_table_payload(table_payload)
        if dataframe is not None:
            tables[str(name)] = dataframe

    return tables


def _dataframe_from_table_payload(value: Any) -> pd.DataFrame | None:
    if isinstance(value, pd.DataFrame):
        return value

    if not isinstance(value, Mapping):
        return None

    records = value.get("records")
    columns = value.get("columns")

    if not isinstance(records, list):
        return None

    if isinstance(columns, list):
        return pd.DataFrame.from_records(
            records, columns=[str(item) for item in columns]
        )

    return pd.DataFrame.from_records(records)


def _first_dataframe(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame | None:
    preferred_names = (
        "main",
        "table",
        "comparison",
        "forecast",
        "actual_and_forecast",
        "backtest_results",
        "actual_vs_predicted",
    )

    for name in preferred_names:
        dataframe = tables.get(name)
        if isinstance(dataframe, pd.DataFrame):
            return dataframe

    for dataframe in tables.values():
        if isinstance(dataframe, pd.DataFrame):
            return dataframe

    return None


def _app_error_from_payload(value: Any) -> AppError | None:
    if value is None:
        return None

    if isinstance(value, AppError):
        return value

    if not isinstance(value, Mapping):
        return AppError(
            code="backend_error",
            title="Backend error",
            user_message=str(value),
        )

    details = value.get("details")
    field_errors: dict[str, str] = {}
    if isinstance(details, Mapping):
        field_errors = {str(key): str(item) for key, item in details.items()}

    code = str(value.get("code") or "backend_error")
    title = str(value.get("title") or value.get("message") or "Backend error")
    user_message = str(
        value.get("user_message")
        or value.get("message")
        or "The backend could not complete the request."
    )

    technical_detail = value.get("technical_detail")
    if technical_detail is None and details:
        technical_detail = str(details)

    return AppError(
        code=code,
        title=title,
        user_message=user_message,
        technical_detail=(
            str(technical_detail) if technical_detail is not None else None
        ),
        field_errors=field_errors,
    )


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
