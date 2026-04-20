from __future__ import annotations

import inspect
from typing import Any

import pandas as pd

from country_compare.services.results import AppMessage, ComparisonResult, PresentationResult


class PresentationService:
    """Convert raw comparison outputs into UI-ready artifacts."""

    def build_single_metric_presentation(
        self,
        result: ComparisonResult,
    ) -> PresentationResult:
        if not result.ok:
            return PresentationResult(
                mode=result.mode,
                request=result.request,
                error=result.error,
                warnings=list(result.warnings),
                diagnostics=dict(result.diagnostics),
            )

        table = self._build_single_metric_table(result.dataframe, result.request)
        chart = self._build_single_metric_chart(result.dataframe, result.request)
        summary = self._build_single_metric_summary(result.dataframe, result.metadata)
        metadata = self._build_single_metric_metadata(result.metadata)
        messages = self._build_messages(result)

        return PresentationResult(
            mode=result.mode,
            request=result.request,
            summary=summary,
            table=table,
            chart=chart,
            metadata=metadata,
            diagnostics=dict(result.diagnostics),
            warnings=list(result.warnings),
            messages=messages,
        )

    def _build_single_metric_table(self, dataframe: pd.DataFrame, request: Any) -> pd.DataFrame:
        try:
            from country_compare.output.tables import make_single_metric_table

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "top_n": getattr(request, "top_n", None),
            }
            rendered = _invoke_callable_with_supported_kwargs(make_single_metric_table, aliases)
            if isinstance(rendered, pd.DataFrame):
                return rendered
        except Exception:
            pass

        preferred_columns = [
            "rank",
            "country_code",
            "country_name",
            "metric_name",
            "value",
            "normalized_value",
            "year",
            "unit",
            "normalization_method",
        ]
        present_columns = [column for column in preferred_columns if column in dataframe.columns]
        fallback = dataframe.loc[:, present_columns].copy() if present_columns else dataframe.copy()
        if getattr(request, "top_n", None):
            fallback = fallback.head(int(request.top_n)).copy()
        return fallback

    def _build_single_metric_chart(self, dataframe: pd.DataFrame, request: Any) -> Any:
        try:
            from country_compare.output.charts import plot_single_metric_ranking

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "top_n": getattr(request, "top_n", None),
                "title": None,
            }
            rendered = _invoke_callable_with_supported_kwargs(plot_single_metric_ranking, aliases)
            if isinstance(rendered, tuple) and rendered:
                return rendered[0]
            return rendered
        except Exception:
            return None

    def _build_single_metric_summary(
        self,
        dataframe: pd.DataFrame,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if dataframe.empty:
            return {
                "status": "empty",
                "title": "No rows returned",
                "description": "The comparison ran successfully but returned no rows.",
            }

        best_row = self._resolve_top_row(dataframe)
        top_country = best_row.get("country_name") or best_row.get("country_code")
        top_value = best_row.get("value")
        top_rank = best_row.get("rank")

        return {
            "status": "success",
            "title": metadata.get("metric_display_name", metadata.get("metric_id", "Metric comparison")),
            "description": f"Compared {len(dataframe)} row(s) across {len(metadata.get('selected_countries', []))} selected countries.",
            "top_country": top_country,
            "top_rank": top_rank,
            "top_value": top_value,
        }

    def _build_single_metric_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "Selection": {
                "Metric": metadata.get("metric_display_name") or metadata.get("metric_id"),
                "Metric ID": metadata.get("metric_id"),
                "Countries": ", ".join(metadata.get("selected_countries", [])),
                "Year strategy": metadata.get("year_strategy"),
                "Target year": metadata.get("target_year"),
            },
            "Data": {
                "Rows returned": metadata.get("result_row_count"),
                "Years used": metadata.get("years_used"),
                "Normalization methods": metadata.get("normalization_methods"),
                "Unit": metadata.get("metric_unit"),
                "Category": metadata.get("metric_category"),
            },
        }

    def _build_messages(self, result: ComparisonResult) -> list[AppMessage]:
        messages: list[AppMessage] = []
        for warning in result.warnings:
            messages.append(AppMessage(level="warning", text=warning))
        if result.ok and result.dataframe is not None and not result.dataframe.empty:
            messages.append(AppMessage(level="success", text="Comparison completed successfully."))
        return messages

    def _resolve_top_row(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        if "rank" in dataframe.columns:
            row = dataframe.sort_values(by="rank", ascending=True).iloc[0]
            return row.to_dict()
        if "normalized_value" in dataframe.columns:
            row = dataframe.sort_values(by="normalized_value", ascending=False).iloc[0]
            return row.to_dict()
        row = dataframe.iloc[0]
        return row.to_dict()


def _invoke_callable_with_supported_kwargs(func: Any, aliases: dict[str, Any]) -> Any:
    signature = inspect.signature(func)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL,):
            continue
        if name in aliases and aliases[name] is not None:
            kwargs[name] = aliases[name]
    return func(**kwargs)
