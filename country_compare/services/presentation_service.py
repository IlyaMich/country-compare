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
            return self._error_presentation(result)

        table = self._build_single_metric_table(result.dataframe, result.request)
        chart = self._build_single_metric_chart(result.dataframe, result.request)
        summary = self._build_single_metric_summary(result.dataframe, result.metadata)
        metadata = self._build_single_metric_metadata(result.metadata)
        messages = self._build_messages(result, success_text="Single-metric comparison completed successfully.")

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

    def build_multi_metric_presentation(
        self,
        result: ComparisonResult,
    ) -> PresentationResult:
        if not result.ok:
            return self._error_presentation(result)

        long_table = self._build_multi_metric_long_table(result.dataframe, result.request)
        wide_table = self._build_multi_metric_wide_table(result.dataframe, result.request)
        chart = self._build_multi_metric_chart(result.dataframe, result.request)
        summary = self._build_multi_metric_summary(result.dataframe, result.metadata)
        metadata = self._build_multi_metric_metadata(result.metadata)
        messages = self._build_messages(result, success_text="Multi-metric comparison completed successfully.")

        tables: dict[str, pd.DataFrame] = {}
        if wide_table is not None:
            tables["Wide comparison table"] = wide_table

        return PresentationResult(
            mode=result.mode,
            request=result.request,
            summary=summary,
            table=long_table,
            chart=chart,
            tables=tables,
            metadata=metadata,
            diagnostics=dict(result.diagnostics),
            warnings=list(result.warnings),
            messages=messages,
        )

    def build_weighted_score_presentation(
        self,
        result: ComparisonResult,
    ) -> PresentationResult:
        if not result.ok:
            return self._error_presentation(result)

        table = self._build_weighted_score_table(result.dataframe, result.request)
        chart = self._build_weighted_score_chart(result.dataframe, result.request)
        summary = self._build_weighted_score_summary(result.dataframe, result.metadata)
        metadata = self._build_weighted_score_metadata(result.metadata)
        messages = self._build_messages(result, success_text="Weighted scoring completed successfully.")

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

    def _error_presentation(self, result: ComparisonResult) -> PresentationResult:
        return PresentationResult(
            mode=result.mode,
            request=result.request,
            error=result.error,
            warnings=list(result.warnings),
            diagnostics=dict(result.diagnostics),
        )

    def _build_single_metric_table(self, dataframe: pd.DataFrame, request: Any) -> pd.DataFrame:
        try:
            from country_compare.output.tables import make_single_metric_table

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "top_n": getattr(request, "top_n", None),
                "round_ndigits": 3,
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

        best_row = self._resolve_top_row(dataframe, rank_column="rank", value_column="normalized_value")
        top_country = best_row.get("country_name") or best_row.get("country_code")
        top_value = best_row.get("value")
        top_rank = best_row.get("rank")

        return {
            "status": "success",
            "title": metadata.get("metric_display_name", metadata.get("metric_id", "Metric comparison")),
            "description": (
                f"Compared {len(dataframe)} row(s) across "
                f"{len(metadata.get('selected_countries', []))} selected countries."
            ),
            "top_country": top_country,
            "top_rank": top_rank,
            "top_value": top_value,
        }

    def _build_single_metric_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "Selection": {
                "Metric": metadata.get("metric_display_name") or metadata.get("metric_id"),
                "Metric ID": metadata.get("metric_id"),
                "Countries": metadata.get("selected_countries"),
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

    def _build_multi_metric_long_table(self, dataframe: pd.DataFrame, request: Any) -> pd.DataFrame:
        try:
            from country_compare.output.tables import make_multi_metric_long_table

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "top_n": getattr(request, "top_n", None),
                "round_ndigits": 3,
            }
            rendered = _invoke_callable_with_supported_kwargs(make_multi_metric_long_table, aliases)
            if isinstance(rendered, pd.DataFrame):
                return rendered
        except Exception:
            pass
        return dataframe.copy()

    def _build_multi_metric_wide_table(self, dataframe: pd.DataFrame, request: Any) -> pd.DataFrame | None:
        try:
            from country_compare.comparison.multi_metric import build_multi_metric_wide_table
            from country_compare.output.tables import make_multi_metric_wide_table

            wide_df = build_multi_metric_wide_table(dataframe)
            aliases = {
                "df": wide_df,
                "dataframe": wide_df,
                "data": wide_df,
                "top_n": getattr(request, "top_n", None),
                "round_ndigits": 3,
            }
            rendered = _invoke_callable_with_supported_kwargs(make_multi_metric_wide_table, aliases)
            if isinstance(rendered, pd.DataFrame):
                return rendered
            if isinstance(wide_df, pd.DataFrame):
                return wide_df
        except Exception:
            return None
        return None

    def _build_multi_metric_chart(self, dataframe: pd.DataFrame, request: Any) -> Any:
        try:
            from country_compare.output.charts import plot_multi_metric_heatmap

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "title": None,
            }
            rendered = _invoke_callable_with_supported_kwargs(plot_multi_metric_heatmap, aliases)
            if isinstance(rendered, tuple) and rendered:
                return rendered[0]
            return rendered
        except Exception:
            return None

    def _build_multi_metric_summary(
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

        ranked = dataframe.copy()
        top_country = "—"
        if {"country_code", "normalized_value"}.issubset(ranked.columns):
            summary_df = (
                ranked.groupby(["country_code", "country_name"], dropna=False)["normalized_value"]
                .mean()
                .sort_values(ascending=False)
                .reset_index()
            )
            if not summary_df.empty:
                row = summary_df.iloc[0]
                top_country = row.get("country_name") or row.get("country_code")

        return {
            "status": "success",
            "title": "Multi-metric comparison",
            "description": (
                f"Compared {len(metadata.get('metric_ids', []))} selected metric(s) across "
                f"{len(metadata.get('selected_countries', []))} selected countries."
            ),
            "top_country": top_country,
            "top_rank": "—",
            "top_value": len(metadata.get("metrics_returned", [])),
        }

    def _build_multi_metric_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        metric_labels = metadata.get("metric_labels", {}) or {}
        metric_display = [
            f"{metric_labels.get(metric_id, metric_id)} ({metric_id})"
            for metric_id in metadata.get("metric_ids", [])
        ]

        return {
            "Selection": {
                "Metrics": metric_display,
                "Countries": metadata.get("selected_countries"),
                "Year strategy": metadata.get("year_strategy"),
                "Target year": metadata.get("target_year"),
            },
            "Data": {
                "Rows returned": metadata.get("result_row_count"),
                "Countries returned": metadata.get("countries_returned"),
                "Metrics returned": metadata.get("metrics_returned"),
                "Years used": metadata.get("years_used"),
                "Normalization methods": metadata.get("normalization_methods"),
            },
        }

    def _build_weighted_score_table(self, dataframe: pd.DataFrame, request: Any) -> pd.DataFrame:
        try:
            from country_compare.output.tables import make_weighted_score_table

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "top_n": getattr(request, "top_n", None),
                "round_ndigits": 3,
            }
            rendered = _invoke_callable_with_supported_kwargs(make_weighted_score_table, aliases)
            if isinstance(rendered, pd.DataFrame):
                return rendered
        except Exception:
            pass
        return dataframe.copy()

    def _build_weighted_score_chart(self, dataframe: pd.DataFrame, request: Any) -> Any:
        try:
            from country_compare.output.charts import plot_weighted_scores

            aliases = {
                "df": dataframe,
                "dataframe": dataframe,
                "data": dataframe,
                "title": None,
            }
            rendered = _invoke_callable_with_supported_kwargs(plot_weighted_scores, aliases)
            if isinstance(rendered, tuple) and rendered:
                return rendered[0]
            return rendered
        except Exception:
            return None

    def _build_weighted_score_summary(
        self,
        dataframe: pd.DataFrame,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if dataframe.empty:
            return {
                "status": "empty",
                "title": "No rows returned",
                "description": "The weighted scoring ran successfully but returned no rows.",
            }

        best_row = self._resolve_top_row(
            dataframe,
            rank_column="score_rank",
            value_column="weighted_score",
        )
        top_country = best_row.get("country_name") or best_row.get("country_code")

        return {
            "status": "success",
            "title": f"Weighted score — {metadata.get('profile_name', 'profile')}",
            "description": (
                f"Scored {len(dataframe)} country row(s) using profile "
                f"'{metadata.get('profile_name', 'unknown')}'."
            ),
            "top_country": top_country,
            "top_rank": best_row.get("score_rank"),
            "top_value": best_row.get("weighted_score"),
        }

    def _build_weighted_score_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "Selection": {
                "Profile": metadata.get("profile_name"),
                "Countries": metadata.get("selected_countries"),
                "Profile year strategy": metadata.get("profile_year_strategy"),
                "Target year": metadata.get("target_year"),
                "Missing-data policy": metadata.get("missing_data_policy"),
            },
            "Resolved profile": {
                "Weights": metadata.get("resolved_weights"),
            },
            "Data": {
                "Rows returned": metadata.get("result_row_count"),
                "Countries returned": metadata.get("countries_returned"),
            },
        }

    def _build_messages(
        self,
        result: ComparisonResult,
        *,
        success_text: str,
    ) -> list[AppMessage]:
        messages: list[AppMessage] = []
        for warning in result.warnings:
            messages.append(AppMessage(level="warning", text=warning))
        if result.ok and result.dataframe is not None and not result.dataframe.empty:
            messages.append(AppMessage(level="success", text=success_text))
        return messages

    def _resolve_top_row(
        self,
        dataframe: pd.DataFrame,
        *,
        rank_column: str,
        value_column: str,
    ) -> dict[str, Any]:
        if rank_column in dataframe.columns:
            row = dataframe.sort_values(by=rank_column, ascending=True).iloc[0]
            return row.to_dict()
        if value_column in dataframe.columns:
            row = dataframe.sort_values(by=value_column, ascending=False).iloc[0]
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