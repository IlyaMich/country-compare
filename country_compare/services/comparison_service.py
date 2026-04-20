from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from country_compare.comparison.single_metric import ComparisonError
from country_compare.config import load_configuration_bundle
from country_compare.config.models import YearStrategy
from country_compare.config.validator import ConfigurationValidationError
from country_compare.data import load_metric_dataframe
from country_compare.data.stores.registry import create_metric_store
from country_compare.scoring.weighted_score import ScoringError, resolve_scoring_profile
from country_compare.services.errors import AppError
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)
from country_compare.services.results import ComparisonResult


class ComparisonService:
    """Framework-neutral orchestration for comparison flows."""

    def __init__(
        self,
        *,
        context: Any,
        dataset_service: Any | None = None,
        config_service: Any | None = None,
    ) -> None:
        self.context = context
        self.dataset_service = dataset_service
        self.config_service = config_service

    def run_single_metric(self, request: SingleMetricRequest) -> ComparisonResult:
        return self._run_request(
            request=request,
            validator=self._validate_single_metric_request,
            executor=self._invoke_single_metric_compare,
            metadata_builder=self._build_single_metric_metadata,
            diagnostics_builder=self._build_single_metric_diagnostics,
            default_mode="single_metric",
        )

    def run_multi_metric(self, request: MultiMetricRequest) -> ComparisonResult:
        return self._run_request(
            request=request,
            validator=self._validate_multi_metric_request,
            executor=self._invoke_multi_metric_compare,
            metadata_builder=self._build_multi_metric_metadata,
            diagnostics_builder=self._build_multi_metric_diagnostics,
            default_mode="multi_metric",
        )

    def run_weighted_score(self, request: WeightedScoreRequest) -> ComparisonResult:
        return self._run_request(
            request=request,
            validator=self._validate_weighted_score_request,
            executor=self._invoke_weighted_score,
            metadata_builder=self._build_weighted_score_metadata,
            diagnostics_builder=self._build_weighted_score_diagnostics,
            default_mode="weighted_score",
        )

    def _run_request(
        self,
        *,
        request: Any,
        validator: Any,
        executor: Any,
        metadata_builder: Any,
        diagnostics_builder: Any,
        default_mode: str,
    ) -> ComparisonResult:
        try:
            bundle = self._load_configuration_bundle()
            dataframe = self._load_dataframe()
            validator(request, dataframe=dataframe, bundle=bundle)

            raw_output = executor(
                dataframe=dataframe,
                bundle=bundle,
                request=request,
            )
            result_df, extra_metadata = self._coerce_comparison_output(raw_output)

            warnings = self._build_result_warnings(
                request=request,
                dataframe=result_df,
            )
            metadata = metadata_builder(
                request=request,
                dataframe=result_df,
                bundle=bundle,
            )
            metadata.update(extra_metadata)

            return ComparisonResult(
                mode=getattr(request, "mode", default_mode),
                request=request,
                dataframe=result_df,
                metadata=metadata,
                diagnostics=diagnostics_builder(result_df),
                warnings=warnings,
            )
        except Exception as exc:  # pragma: no cover - exercised via mapping-focused tests
            return ComparisonResult(
                mode=getattr(request, "mode", default_mode),
                request=request,
                error=self._map_exception(exc),
            )

    def _validate_single_metric_request(
        self,
        request: SingleMetricRequest,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> None:
        field_errors: dict[str, str] = {}

        if len(request.countries) < 2:
            field_errors["countries"] = "Select at least two countries to compare."

        if request.metric_id not in bundle.metrics.metrics:
            field_errors["metric_id"] = f"Unknown metric_id: {request.metric_id}"

        if request.year_strategy == YearStrategy.TARGET_YEAR and request.target_year is None:
            field_errors["target_year"] = "A target year is required for target-year mode."

        available_countries = self._available_country_codes(dataframe)
        missing_countries = [code for code in request.countries if code not in available_countries]
        if missing_countries:
            field_errors["countries"] = (
                "The dataset does not contain these selected countries: "
                + ", ".join(sorted(missing_countries))
            )

        metric_rows = dataframe.loc[dataframe["metric_id"].astype("string") == request.metric_id]
        if metric_rows.empty:
            field_errors["metric_id"] = (
                f"The dataset does not contain rows for metric_id '{request.metric_id}'."
            )

        if field_errors:
            raise ValueError(field_errors)

    def _validate_multi_metric_request(
        self,
        request: MultiMetricRequest,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> None:
        field_errors: dict[str, str] = {}

        if len(request.countries) < 2:
            field_errors["countries"] = "Select at least two countries to compare."

        if not request.metric_ids:
            field_errors["metric_ids"] = "Select at least one metric."

        unknown_metrics = [metric_id for metric_id in request.metric_ids if metric_id not in bundle.metrics.metrics]
        if unknown_metrics:
            field_errors["metric_ids"] = (
                "Unknown metric_id values: " + ", ".join(sorted(unknown_metrics))
            )

        if request.year_strategy == YearStrategy.TARGET_YEAR and request.target_year is None:
            field_errors["target_year"] = "A target year is required for target-year mode."

        available_countries = self._available_country_codes(dataframe)
        missing_countries = [code for code in request.countries if code not in available_countries]
        if missing_countries:
            field_errors["countries"] = (
                "The dataset does not contain these selected countries: "
                + ", ".join(sorted(missing_countries))
            )

        available_metrics = self._available_metric_ids(dataframe)
        missing_metrics = [metric_id for metric_id in request.metric_ids if metric_id not in available_metrics]
        if missing_metrics:
            field_errors["metric_ids"] = (
                "The dataset does not contain rows for these metric_id values: "
                + ", ".join(sorted(missing_metrics))
            )

        if field_errors:
            raise ValueError(field_errors)

    def _validate_weighted_score_request(
        self,
        request: WeightedScoreRequest,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> None:
        field_errors: dict[str, str] = {}

        if len(request.countries) < 2:
            field_errors["countries"] = "Select at least two countries to score."

        if request.profile_name not in bundle.scoring.profiles:
            field_errors["profile_name"] = f"Unknown scoring profile: {request.profile_name}"
        else:
            resolved_profile = resolve_scoring_profile(
                bundle.metrics,
                bundle.scoring,
                profile_name=request.profile_name,
            )
            if resolved_profile.year_strategy == YearStrategy.TARGET_YEAR and request.target_year is None:
                field_errors["target_year"] = (
                    "This scoring profile uses target-year mode, so a target year is required."
                )

            available_metrics = self._available_metric_ids(dataframe)
            missing_profile_metrics = [
                metric_id for metric_id in resolved_profile.weights if metric_id not in available_metrics
            ]
            if missing_profile_metrics:
                field_errors["profile_name"] = (
                    "The dataset is missing rows for one or more metrics required by the selected "
                    "profile: " + ", ".join(sorted(missing_profile_metrics))
                )

        available_countries = self._available_country_codes(dataframe)
        missing_countries = [code for code in request.countries if code not in available_countries]
        if missing_countries:
            field_errors["countries"] = (
                "The dataset does not contain these selected countries: "
                + ", ".join(sorted(missing_countries))
            )

        if field_errors:
            raise ValueError(field_errors)

    def _load_dataframe(self) -> pd.DataFrame:
        if self.dataset_service is not None and hasattr(self.dataset_service, "load_dataframe"):
            return self.dataset_service.load_dataframe()

        store = self._create_store_from_context()
        return load_metric_dataframe(store=store)

    def _load_configuration_bundle(self) -> Any:
        if self.config_service is not None and hasattr(self.config_service, "load_bundle"):
            return self.config_service.load_bundle()

        return load_configuration_bundle(
            self.context.metrics_config_path,
            self.context.scoring_config_path,
            validate=True,
        )

    def _create_store_from_context(self) -> Any:
        kwargs: dict[str, Any] = {}
        store_path = getattr(self.context, "store_path", None)
        if store_path:
            kwargs["path"] = Path(store_path)
        backend = getattr(self.context, "store_backend", "parquet")
        return create_metric_store(backend=backend, **kwargs)

    def _invoke_single_metric_compare(
        self,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
        request: SingleMetricRequest,
    ) -> Any:
        from country_compare.comparison.single_metric import compare_metric

        metric_cfg = bundle.metrics.metrics.get(request.metric_id)
        aliases = {
            "df": dataframe,
            "dataframe": dataframe,
            "data": dataframe,
            "bundle": bundle,
            "config_bundle": bundle,
            "configuration_bundle": bundle,
            "metrics_config": bundle.metrics,
            "scoring_config": bundle.scoring,
            "metric_id": request.metric_id,
            "metric": request.metric_id,
            "selected_metric": request.metric_id,
            "countries": request.countries,
            "country_codes": request.countries,
            "selected_countries": request.countries,
            "countries_include": request.countries,
            "year_strategy": request.year_strategy,
            "target_year": request.target_year,
            "normalization_method": getattr(metric_cfg, "normalization_method", None),
            "top_n": request.top_n,
        }
        return _invoke_callable_with_supported_kwargs(compare_metric, aliases)

    def _invoke_multi_metric_compare(
        self,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
        request: MultiMetricRequest,
    ) -> Any:
        from country_compare.comparison.multi_metric import compare_countries

        aliases = {
            "df": dataframe,
            "dataframe": dataframe,
            "data": dataframe,
            "bundle": bundle,
            "config_bundle": bundle,
            "configuration_bundle": bundle,
            "metrics_config": bundle.metrics,
            "scoring_config": bundle.scoring,
            "metric_ids": request.metric_ids,
            "metrics": request.metric_ids,
            "selected_metrics": request.metric_ids,
            "countries": request.countries,
            "country_codes": request.countries,
            "selected_countries": request.countries,
            "countries_include": request.countries,
            "year_strategy": request.year_strategy,
            "target_year": request.target_year,
            "top_n": request.top_n,
        }
        return _invoke_callable_with_supported_kwargs(compare_countries, aliases)

    def _invoke_weighted_score(
        self,
        *,
        dataframe: pd.DataFrame,
        bundle: Any,
        request: WeightedScoreRequest,
    ) -> Any:
        from country_compare.scoring.weighted_score import score_countries

        aliases = {
            "df": dataframe,
            "dataframe": dataframe,
            "data": dataframe,
            "bundle": bundle,
            "config_bundle": bundle,
            "configuration_bundle": bundle,
            "metrics_config": bundle.metrics,
            "scoring_config": bundle.scoring,
            "profile_name": request.profile_name,
            "selected_profile": request.profile_name,
            "countries": request.countries,
            "country_codes": request.countries,
            "selected_countries": request.countries,
            "countries_include": request.countries,
            "target_year": request.target_year,
            "top_n": request.top_n,
        }
        return _invoke_callable_with_supported_kwargs(score_countries, aliases)

    def _coerce_comparison_output(self, raw_output: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
        if isinstance(raw_output, pd.DataFrame):
            return raw_output.copy(), {}

        if isinstance(raw_output, tuple):
            if len(raw_output) >= 2 and isinstance(raw_output[0], pd.DataFrame) and isinstance(raw_output[1], dict):
                return raw_output[0].copy(), dict(raw_output[1])
            if len(raw_output) >= 1 and isinstance(raw_output[0], pd.DataFrame):
                return raw_output[0].copy(), {}

        for dataframe_attr in ("dataframe", "result", "results", "table"):
            value = getattr(raw_output, dataframe_attr, None)
            if isinstance(value, pd.DataFrame):
                metadata = getattr(raw_output, "metadata", {}) or {}
                if is_dataclass(metadata):
                    metadata = asdict(metadata)
                return value.copy(), dict(metadata)

        raise TypeError(
            "comparison call returned an unsupported result type. Expected a DataFrame, "
            "(DataFrame, metadata) tuple, or object with a DataFrame attribute."
        )

    def _build_result_warnings(
        self,
        *,
        request: Any,
        dataframe: pd.DataFrame,
    ) -> list[str]:
        warnings: list[str] = []

        if dataframe.empty:
            warnings.append(
                "The selection produced no comparison rows. Try a different selection or year strategy."
            )
            return warnings

        if "country_code" in dataframe.columns:
            returned_countries = {
                str(value).upper()
                for value in dataframe["country_code"].dropna().astype("string").tolist()
            }
            missing_countries = [
                code for code in getattr(request, "countries", []) if code not in returned_countries
            ]
            if missing_countries:
                warnings.append(
                    "Some selected countries are not present in the result: "
                    + ", ".join(sorted(missing_countries))
                )

        if getattr(request, "mode", "") == "weighted_score":
            if "missing_metric_count" in dataframe.columns and dataframe["missing_metric_count"].fillna(0).gt(0).any():
                warnings.append(
                    "Some weighted scores were computed with missing metrics. Review the diagnostics and "
                    "missing-data columns in the result table."
                )

        return warnings

    def _build_single_metric_metadata(
        self,
        *,
        request: SingleMetricRequest,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> dict[str, Any]:
        metric_cfg = bundle.metrics.metrics[request.metric_id]
        years_used = self._extract_years_used(dataframe)
        methods_used = self._extract_string_values(dataframe, "normalization_method")

        return {
            "metric_id": request.metric_id,
            "metric_display_name": metric_cfg.display_name,
            "metric_category": metric_cfg.category,
            "metric_unit": metric_cfg.unit,
            "year_strategy": request.year_strategy.value,
            "target_year": request.target_year,
            "selected_countries": list(request.countries),
            "result_row_count": int(len(dataframe)),
            "years_used": years_used,
            "normalization_methods": methods_used,
        }

    def _build_multi_metric_metadata(
        self,
        *,
        request: MultiMetricRequest,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> dict[str, Any]:
        metric_labels = {
            metric_id: bundle.metrics.metrics[metric_id].display_name
            for metric_id in request.metric_ids
            if metric_id in bundle.metrics.metrics
        }
        return {
            "metric_ids": list(request.metric_ids),
            "metric_labels": metric_labels,
            "selected_countries": list(request.countries),
            "year_strategy": request.year_strategy.value,
            "target_year": request.target_year,
            "result_row_count": int(len(dataframe)),
            "countries_returned": self._extract_string_values(dataframe, "country_code"),
            "metrics_returned": self._extract_string_values(dataframe, "metric_id"),
            "years_used": self._extract_years_used(dataframe),
            "normalization_methods": self._extract_string_values(dataframe, "normalization_method"),
        }

    def _build_weighted_score_metadata(
        self,
        *,
        request: WeightedScoreRequest,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> dict[str, Any]:
        resolved_profile = resolve_scoring_profile(
            bundle.metrics,
            bundle.scoring,
            profile_name=request.profile_name,
        )
        return {
            "profile_name": resolved_profile.profile_name,
            "selected_countries": list(request.countries),
            "profile_year_strategy": resolved_profile.year_strategy.value,
            "target_year": request.target_year,
            "missing_data_policy": resolved_profile.missing_data_policy.value,
            "resolved_weights": dict(resolved_profile.weights),
            "result_row_count": int(len(dataframe)),
            "countries_returned": self._extract_string_values(dataframe, "country_code"),
        }

    def _build_single_metric_diagnostics(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        if dataframe is None or dataframe.empty:
            diagnostics["empty_result"] = True
            return diagnostics

        diagnostics["countries_returned"] = self._extract_string_values(dataframe, "country_code")
        diagnostics["ranked"] = "rank" in dataframe.columns
        diagnostics["normalization_applied"] = "normalization_method" in dataframe.columns
        return diagnostics

    def _build_multi_metric_diagnostics(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        if dataframe is None or dataframe.empty:
            diagnostics["empty_result"] = True
            return diagnostics

        diagnostics["countries_returned"] = self._extract_string_values(dataframe, "country_code")
        diagnostics["metrics_returned"] = self._extract_string_values(dataframe, "metric_id")
        diagnostics["years_used"] = self._extract_years_used(dataframe)
        diagnostics["ranked"] = "rank" in dataframe.columns
        diagnostics["normalization_applied"] = "normalization_method" in dataframe.columns
        return diagnostics

    def _build_weighted_score_diagnostics(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        if dataframe is None or dataframe.empty:
            diagnostics["empty_result"] = True
            return diagnostics

        diagnostics["countries_scored"] = self._extract_string_values(dataframe, "country_code")
        diagnostics["score_ranked"] = "score_rank" in dataframe.columns
        if "missing_metric_count" in dataframe.columns:
            diagnostics["countries_with_missing_metrics"] = int(
                dataframe["missing_metric_count"].fillna(0).gt(0).sum()
            )
        return diagnostics

    def _available_country_codes(self, dataframe: pd.DataFrame) -> set[str]:
        return {
            str(value).upper()
            for value in dataframe["country_code"].dropna().astype("string").unique().tolist()
        }

    def _available_metric_ids(self, dataframe: pd.DataFrame) -> set[str]:
        return {
            str(value)
            for value in dataframe["metric_id"].dropna().astype("string").unique().tolist()
        }

    def _extract_years_used(self, dataframe: pd.DataFrame) -> list[int]:
        if "year" not in dataframe.columns:
            return []
        return sorted(
            int(value)
            for value in dataframe["year"].dropna().astype("Int64").unique().tolist()
        )

    def _extract_string_values(self, dataframe: pd.DataFrame, column: str) -> list[str]:
        if column not in dataframe.columns:
            return []
        return sorted(
            {
                str(value)
                for value in dataframe[column].dropna().astype("string").tolist()
                if str(value)
            }
        )

    def _map_exception(self, exc: Exception) -> AppError:
        technical_detail = repr(exc)

        if isinstance(exc, FileNotFoundError):
            return AppError(
                code="resource_not_found",
                title="Missing project resource",
                user_message=str(exc),
                technical_detail=technical_detail,
            )

        if isinstance(exc, (ConfigurationValidationError, PydanticValidationError)):
            return AppError(
                code="config_invalid",
                title="Configuration is invalid",
                user_message="The metrics or scoring configuration could not be loaded.",
                technical_detail=str(exc),
            )

        if isinstance(exc, ValueError) and isinstance(getattr(exc, "args", [None])[0], dict):
            field_errors = dict(exc.args[0])
            return AppError(
                code="selection_invalid",
                title="Selection is invalid",
                user_message="Please fix the highlighted comparison inputs and try again.",
                technical_detail=technical_detail,
                field_errors=field_errors,
            )

        if isinstance(exc, ScoringError):
            return AppError(
                code="scoring_failed",
                title="Weighted scoring failed",
                user_message=str(exc),
                technical_detail=technical_detail,
            )

        if isinstance(exc, ComparisonError):
            return AppError(
                code="comparison_failed",
                title="Comparison failed",
                user_message=str(exc),
                technical_detail=technical_detail,
            )

        message = str(exc).lower()
        if "common year" in message:
            return AppError(
                code="common_year_unavailable",
                title="No valid common year",
                user_message=str(exc),
                technical_detail=technical_detail,
            )
        if "normalization" in message:
            return AppError(
                code="normalization_failed",
                title="Normalization failed",
                user_message=str(exc),
                technical_detail=technical_detail,
            )

        return AppError(
            code="unexpected_error",
            title="Comparison failed",
            user_message="The comparison could not be completed.",
            technical_detail=technical_detail,
        )


def _invoke_callable_with_supported_kwargs(func: Any, aliases: dict[str, Any]) -> Any:
    signature = inspect.signature(func)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL,):
            continue
        if name in aliases and aliases[name] is not None:
            kwargs[name] = aliases[name]
    return func(**kwargs)