from __future__ import annotations

from pathlib import Path

import pandas as pd

from country_compare.data.access import load_metric_dataframe, metric_dataset_exists
from country_compare.data.stores.registry import create_metric_store, list_registered_backends
from country_compare.services.app_context import AppContext
from country_compare.services.errors import AppError, error_from_exception
from country_compare.services.models import CategorySummary, CountryOption, DatasetSummary, MetricOption


class DatasetService:
    """Read-only dataset inspection helpers for UI/API-facing layers."""

    def __init__(self, context: AppContext) -> None:
        self.context = context

    def get_registered_backends(self) -> tuple[str, ...]:
        return tuple(list_registered_backends())

    def create_store(self):
        kwargs: dict[str, object] = {}
        if self.context.store_path is not None:
            kwargs["path"] = self.context.store_path
        return create_metric_store(self.context.store_backend, **kwargs)

    def dataset_exists(self) -> bool:
        try:
            store = self.create_store()
            return bool(metric_dataset_exists(store=store))
        except Exception:
            return False

    def load_dataframe(self) -> pd.DataFrame:
        store = self.create_store()
        return load_metric_dataframe(store=store)

    def get_dataset_summary(self) -> DatasetSummary:
        dataset_path = self._resolve_store_path()

        try:
            store = self.create_store()
            if not metric_dataset_exists(store=store):
                return DatasetSummary(
                    exists=False,
                    backend=self.context.store_backend,
                    dataset_path=str(dataset_path) if dataset_path is not None else None,
                    error=AppError(
                        code="resource_not_found",
                        title="Dataset not found",
                        user_message="No metric dataset is available at the configured store path.",
                        technical_detail=(
                            f"Dataset path does not exist: {dataset_path}"
                            if dataset_path is not None
                            else "Dataset store reported no existing dataset."
                        ),
                    ),
                )

            dataframe = load_metric_dataframe(store=store)
            categories = self._build_category_summaries(dataframe)
            year_min, year_max = self._extract_year_range(dataframe)

            return DatasetSummary(
                exists=True,
                backend=self.context.store_backend,
                dataset_path=str(dataset_path) if dataset_path is not None else None,
                row_count=int(len(dataframe.index)),
                country_count=int(dataframe["country_code"].dropna().nunique()) if "country_code" in dataframe.columns else 0,
                metric_count=int(dataframe["metric_id"].dropna().nunique()) if "metric_id" in dataframe.columns else 0,
                year_min=year_min,
                year_max=year_max,
                available_columns=tuple(str(column) for column in dataframe.columns.tolist()),
                categories=categories,
            )
        except Exception as exc:
            return DatasetSummary(
                exists=False,
                backend=self.context.store_backend,
                dataset_path=str(dataset_path) if dataset_path is not None else None,
                error=error_from_exception(
                    exc,
                    default_title="Dataset error",
                    default_user_message="The dataset could not be inspected.",
                ),
            )

    def list_countries(self) -> tuple[CountryOption, ...]:
        dataframe = self.load_dataframe()
        if dataframe.empty or "country_code" not in dataframe.columns or "country_name" not in dataframe.columns:
            return ()

        unique_pairs = (
            dataframe[["country_code", "country_name"]]
            .dropna(subset=["country_code", "country_name"])
            .drop_duplicates(subset=["country_code"])
            .sort_values(["country_name", "country_code"])
        )

        return tuple(
            CountryOption(code=str(row.country_code), name=str(row.country_name))
            for row in unique_pairs.itertuples(index=False)
        )

    def list_metrics(self) -> tuple[MetricOption, ...]:
        dataframe = self.load_dataframe()
        required_columns = {"metric_id", "metric_name"}
        if dataframe.empty or not required_columns.issubset(dataframe.columns):
            return ()

        available_columns = set(dataframe.columns)
        subset_columns = ["metric_id", "metric_name"]
        if "category" in available_columns:
            subset_columns.append("category")
        if "unit" in available_columns:
            subset_columns.append("unit")

        unique_metrics = (
            dataframe[subset_columns]
            .dropna(subset=["metric_id", "metric_name"])
            .drop_duplicates(subset=["metric_id"])
            .sort_values(["metric_name", "metric_id"])
        )

        return tuple(
            MetricOption(
                metric_id=str(row.metric_id),
                display_name=str(row.metric_name),
                category=str(row.category) if hasattr(row, "category") and pd.notna(row.category) else None,
                unit=str(row.unit) if hasattr(row, "unit") and pd.notna(row.unit) else None,
            )
            for row in unique_metrics.itertuples(index=False)
        )

    def list_years(self) -> tuple[int, ...]:
        dataframe = self.load_dataframe()
        if dataframe.empty or "year" not in dataframe.columns:
            return ()

        year_values = pd.to_numeric(dataframe["year"], errors="coerce").dropna().astype(int)
        return tuple(sorted(year_values.unique().tolist()))

    def get_category_breakdown(self) -> tuple[CategorySummary, ...]:
        dataframe = self.load_dataframe()
        return self._build_category_summaries(dataframe)

    def _build_category_summaries(self, dataframe: pd.DataFrame) -> tuple[CategorySummary, ...]:
        required_columns = {"category", "country_code", "metric_id"}
        if dataframe.empty or not required_columns.issubset(dataframe.columns):
            return ()

        grouped = (
            dataframe.dropna(subset=["category"])
            .groupby("category", dropna=True)
            .agg(
                row_count=("category", "size"),
                country_count=("country_code", "nunique"),
                metric_count=("metric_id", "nunique"),
            )
            .reset_index()
            .sort_values(["row_count", "category"], ascending=[False, True])
        )

        return tuple(
            CategorySummary(
                name=str(row.category),
                row_count=int(row.row_count),
                country_count=int(row.country_count),
                metric_count=int(row.metric_count),
            )
            for row in grouped.itertuples(index=False)
        )

    def _extract_year_range(self, dataframe: pd.DataFrame) -> tuple[int | None, int | None]:
        if dataframe.empty or "year" not in dataframe.columns:
            return None, None

        numeric_years = pd.to_numeric(dataframe["year"], errors="coerce").dropna().astype(int)
        if numeric_years.empty:
            return None, None

        return int(numeric_years.min()), int(numeric_years.max())

    def _resolve_store_path(self) -> Path | None:
        if self.context.store_path is not None:
            return self.context.store_path.resolve()

        try:
            store = self.create_store()
        except Exception:
            return None

        raw_path = getattr(store, "path", None)
        if raw_path is None:
            return None
        return Path(raw_path).resolve()
