from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from country_compare.config import load_configuration_bundle
from country_compare.config.models import YearStrategy
from country_compare.config.validator import ConfigurationValidationError
from country_compare.data import load_metric_dataframe
from country_compare.data.stores.registry import create_metric_store
from country_compare.services.requests import SingleMetricRequest
from country_compare.services.results import ComparisonResult

try:
    from country_compare.services.errors import AppError
except Exception:  # pragma: no cover - fallback only for incomplete Phase A scaffolding
    from dataclasses import dataclass

    @dataclass(slots=True)
    class AppError:  # type: ignore[override]
        code: str
        title: str
        user_message: str
        technical_detail: str | None = None
        field_errors: dict[str, str] | None = None


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
        try:
            bundle = self._load_configuration_bundle()
            dataframe = self._load_dataframe()
            self._validate_single_metric_request(request, dataframe=dataframe, bundle=bundle)

            raw_output = self._invoke_single_metric_compare(
                dataframe=dataframe,
                bundle=bundle,
                request=request,
            )
            result_df, extra_metadata = self._coerce_comparison_output(raw_output)

            warnings: list[str] = []
            if result_df.empty:
                warnings.append(
                    "The selection produced no comparison rows. Try a different metric, "
                    "country set, or year strategy."
                )

            metadata = self._build_single_metric_metadata(
                request=request,
                dataframe=result_df,
                bundle=bundle,
            )
            metadata.update(extra_metadata)

            return ComparisonResult(
                mode=request.mode,
                request=request,
                dataframe=result_df,
                metadata=metadata,
                diagnostics=self._build_single_metric_diagnostics(result_df),
                warnings=warnings,
            )
        except Exception as exc:  # pragma: no cover - exercised via mapping-focused tests
            return ComparisonResult(
                mode="single_metric",
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

        available_countries = {
            str(value).upper()
            for value in dataframe["country_code"].dropna().astype("string").unique().tolist()
        }
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
            "year_strategy": request.year_strategy,
            "target_year": request.target_year,
            "normalization_method": getattr(metric_cfg, "normalization_method", None),
            "top_n": request.top_n,
        }
        return _invoke_callable_with_supported_kwargs(compare_metric, aliases)

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
            "compare_metric returned an unsupported result type. Expected a DataFrame, "
            "(DataFrame, metadata) tuple, or object with a DataFrame attribute."
        )

    def _build_single_metric_metadata(
        self,
        *,
        request: SingleMetricRequest,
        dataframe: pd.DataFrame,
        bundle: Any,
    ) -> dict[str, Any]:
        metric_cfg = bundle.metrics.metrics[request.metric_id]
        years_used = sorted(
            int(value)
            for value in dataframe["year"].dropna().astype("Int64").unique().tolist()
        ) if "year" in dataframe.columns else []

        methods_used = sorted(
            str(value)
            for value in dataframe.get("normalization_method", pd.Series(dtype="string"))
            .dropna()
            .astype("string")
            .unique()
            .tolist()
        )

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

    def _build_single_metric_diagnostics(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        if dataframe is None or dataframe.empty:
            diagnostics["empty_result"] = True
            return diagnostics

        if "country_code" in dataframe.columns:
            diagnostics["countries_returned"] = sorted(
                dataframe["country_code"].dropna().astype("string").astype(str).tolist()
            )
        if "rank" in dataframe.columns:
            diagnostics["ranked"] = True
        if "normalization_method" in dataframe.columns:
            diagnostics["normalization_applied"] = True
        return diagnostics

    def _map_exception(self, exc: Exception) -> AppError:
        technical_detail = repr(exc)

        if isinstance(exc, FileNotFoundError):
            return AppError(
                code="resource_not_found",
                title="Missing project resource",
                user_message=str(exc),
                technical_detail=technical_detail,
            )

        if isinstance(exc, ConfigurationValidationError | PydanticValidationError):
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
