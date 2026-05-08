from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd

from country_compare.data.access import load_metric_dataframe, metric_dataset_exists
from country_compare.data.contract import (
    CATEGORY_COLUMN,
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    UNIT_COLUMN,
    YEAR_COLUMN,
)
from country_compare.data.manifest import (
    compute_file_sha256,
    default_manifest_path_for_dataset,
    read_manifest,
    validate_manifest_against_dataset,
)
from country_compare.data.stores.registry import (
    create_metric_store,
    list_registered_backends,
)
from country_compare.data.validation import validate_dataframe
from country_compare.services.app_context import AppContext
from country_compare.services.errors import AppError, error_from_exception
from country_compare.services.models import (
    CategorySummary,
    CountryOption,
    DatasetSummary,
    MetricOption,
)


class _DatasetFileMetadata(TypedDict):
    checksum: str | None
    size_bytes: int | None
    modified_at: str | None


class DatasetService:
    """Read-only dataset inspection helpers for UI/API-facing layers."""

    def __init__(self, context: AppContext) -> None:
        self.context = context

    def get_registered_backends(self) -> tuple[str, ...]:
        return tuple(list_registered_backends())

    def create_store(self) -> Any:
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
        manifest_path = self._resolve_manifest_path(dataset_path)

        try:
            store = self.create_store()
            if not metric_dataset_exists(store=store):
                return DatasetSummary(
                    exists=False,
                    backend=self.context.store_backend,
                    dataset_path=(
                        str(dataset_path) if dataset_path is not None else None
                    ),
                    manifest_path=(
                        str(manifest_path) if manifest_path is not None else None
                    ),
                    manifest_exists=(
                        bool(manifest_path.exists())
                        if manifest_path is not None
                        else False
                    ),
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
            return self._build_dataset_summary_from_dataframe(
                dataframe,
                dataset_path=dataset_path,
                manifest_path=manifest_path,
            )
        except Exception as exc:
            dataset_stat = self._build_dataset_file_metadata(dataset_path)
            manifest_validation = self._validate_manifest(
                dataset_path=dataset_path,
                manifest_path=manifest_path,
                dataframe=None,
            )
            manifest_issues = self._manifest_issue_messages(manifest_validation)
            schema_issues = (str(exc),)
            return DatasetSummary(
                exists=bool(dataset_path is not None and dataset_path.exists()),
                backend=self.context.store_backend,
                dataset_path=str(dataset_path) if dataset_path is not None else None,
                dataset_checksum=dataset_stat["checksum"],
                dataset_size_bytes=dataset_stat["size_bytes"],
                dataset_modified_at=dataset_stat["modified_at"],
                manifest_path=str(manifest_path) if manifest_path is not None else None,
                manifest_exists=(
                    bool(manifest_path.exists()) if manifest_path is not None else False
                ),
                manifest_valid=(
                    bool(manifest_validation.valid)
                    if manifest_validation is not None
                    else False
                ),
                manifest_issue_count=len(manifest_issues),
                manifest_issues=manifest_issues,
                schema_valid=False,
                schema_issue_count=len(schema_issues),
                schema_issues=schema_issues,
                error=error_from_exception(
                    exc,
                    default_title="Dataset error",
                    default_user_message="The dataset could not be inspected.",
                ),
            )

    def list_countries(self) -> tuple[CountryOption, ...]:
        dataframe = self.load_dataframe()
        if (
            dataframe.empty
            or "country_code" not in dataframe.columns
            or "country_name" not in dataframe.columns
        ):
            return ()

        unique_pairs = (
            dataframe[[COUNTRY_CODE_COLUMN, COUNTRY_NAME_COLUMN]]
            .dropna(subset=[COUNTRY_CODE_COLUMN, COUNTRY_NAME_COLUMN])
            .drop_duplicates(subset=[COUNTRY_CODE_COLUMN])
            .sort_values([COUNTRY_NAME_COLUMN, COUNTRY_CODE_COLUMN])
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
        subset_columns = [METRIC_ID_COLUMN, METRIC_NAME_COLUMN]
        if CATEGORY_COLUMN in available_columns:
            subset_columns.append(CATEGORY_COLUMN)
        if UNIT_COLUMN in available_columns:
            subset_columns.append(UNIT_COLUMN)

        unique_metrics = (
            dataframe[subset_columns]
            .dropna(subset=[METRIC_ID_COLUMN, METRIC_NAME_COLUMN])
            .drop_duplicates(subset=[METRIC_ID_COLUMN])
            .sort_values([METRIC_NAME_COLUMN, METRIC_ID_COLUMN])
        )

        return tuple(
            MetricOption(
                metric_id=str(row.metric_id),
                display_name=str(row.metric_name),
                category=(
                    str(row.category)
                    if hasattr(row, "category") and pd.notna(row.category)
                    else None
                ),
                unit=(
                    str(row.unit)
                    if hasattr(row, "unit") and pd.notna(row.unit)
                    else None
                ),
            )
            for row in unique_metrics.itertuples(index=False)
        )

    def list_years(self) -> tuple[int, ...]:
        dataframe = self.load_dataframe()
        if dataframe.empty or YEAR_COLUMN not in dataframe.columns:
            return ()

        year_values = (
            pd.to_numeric(dataframe[YEAR_COLUMN], errors="coerce").dropna().astype(int)
        )
        return tuple(sorted(year_values.unique().tolist()))

    def get_category_breakdown(self) -> tuple[CategorySummary, ...]:
        dataframe = self.load_dataframe()
        return self._build_category_summaries(dataframe)

    def get_country_catalog(self) -> tuple[CountryOption, ...]:
        return self.list_countries()

    def get_metric_catalog(self) -> tuple[MetricOption, ...]:
        return self.list_metrics()

    def get_dataset_identity(
        self, dataframe: pd.DataFrame | None = None
    ) -> dict[str, Any]:
        """Return a compact identity payload for computation metadata."""

        dataset_path = self._resolve_store_path()
        manifest_path = self._resolve_manifest_path(dataset_path)
        identity: dict[str, Any] = {}

        manifest = self._read_manifest_if_available(manifest_path)
        if manifest:
            field_map = {
                "dataset_version": "dataset_version",
                "dataset_sha256": "sha256",
                "dataset_file": "dataset_file",
                "dataset_created_at": "created_at",
                "schema_version": "schema_version",
            }
            for output_key, manifest_key in field_map.items():
                value = manifest.get(manifest_key)
                if value is not None:
                    identity[output_key] = value

        if dataset_path is not None:
            identity.setdefault("dataset_file", dataset_path.name)
            if dataset_path.exists() and dataset_path.is_file():
                identity.setdefault("dataset_sha256", compute_file_sha256(dataset_path))

        if dataframe is not None:
            versions = self._extract_dataset_versions(dataframe)
            if versions:
                identity.setdefault("dataset_versions", list(versions))
                resolved_version = (
                    versions[0] if len(versions) == 1 else ",".join(versions)
                )
                identity.setdefault("dataset_version", resolved_version)

        return {key: value for key, value in identity.items() if value is not None}

    def _build_dataset_summary_from_dataframe(
        self,
        dataframe: pd.DataFrame,
        *,
        dataset_path: Path | None,
        manifest_path: Path | None,
    ) -> DatasetSummary:
        categories = self._build_category_summaries(dataframe)
        year_min, year_max = self._extract_year_range(dataframe)
        schema_valid, schema_issues = self._validate_schema(dataframe)
        dataset_versions = self._extract_dataset_versions(dataframe)
        dataset_stat = self._build_dataset_file_metadata(dataset_path)
        manifest_validation = self._validate_manifest(
            dataset_path=dataset_path,
            manifest_path=manifest_path,
            dataframe=dataframe,
        )
        manifest = (
            manifest_validation.manifest
            if manifest_validation is not None and manifest_validation.manifest
            else self._read_manifest_if_available(manifest_path)
        )
        manifest_issues = self._manifest_issue_messages(manifest_validation)

        return DatasetSummary(
            exists=True,
            backend=self.context.store_backend,
            dataset_path=str(dataset_path) if dataset_path is not None else None,
            row_count=int(len(dataframe.index)),
            country_count=(
                int(dataframe[COUNTRY_CODE_COLUMN].dropna().nunique())
                if COUNTRY_CODE_COLUMN in dataframe.columns
                else 0
            ),
            metric_count=(
                int(dataframe[METRIC_ID_COLUMN].dropna().nunique())
                if METRIC_ID_COLUMN in dataframe.columns
                else 0
            ),
            year_min=year_min,
            year_max=year_max,
            available_columns=tuple(
                str(column) for column in dataframe.columns.tolist()
            ),
            categories=categories,
            dataset_versions=dataset_versions,
            dataset_checksum=dataset_stat["checksum"],
            dataset_size_bytes=dataset_stat["size_bytes"],
            dataset_modified_at=dataset_stat["modified_at"],
            manifest_path=str(manifest_path) if manifest_path is not None else None,
            manifest_exists=(
                bool(manifest_path.exists()) if manifest_path is not None else False
            ),
            manifest_valid=(
                bool(manifest_validation.valid)
                if manifest_validation is not None
                else False
            ),
            manifest_issue_count=len(manifest_issues),
            manifest_issues=manifest_issues,
            manifest_dataset_version=(
                str(manifest.get("dataset_version"))
                if manifest and manifest.get("dataset_version") is not None
                else None
            ),
            manifest_created_at=(
                str(manifest.get("created_at"))
                if manifest and manifest.get("created_at") is not None
                else None
            ),
            manifest_schema_version=(
                str(manifest.get("schema_version"))
                if manifest and manifest.get("schema_version") is not None
                else None
            ),
            schema_valid=schema_valid,
            schema_issue_count=len(schema_issues),
            schema_issues=schema_issues,
        )

    def _validate_manifest(
        self,
        *,
        dataset_path: Path | None,
        manifest_path: Path | None,
        dataframe: pd.DataFrame | None,
    ):
        if dataset_path is None or manifest_path is None:
            return None
        return validate_manifest_against_dataset(
            manifest_path=manifest_path,
            dataset_path=dataset_path,
            dataframe=dataframe,
        )

    def _manifest_issue_messages(self, validation: Any | None) -> tuple[str, ...]:
        if validation is None:
            return ()
        return tuple(str(message) for message in validation.messages if str(message))

    def _read_manifest_if_available(
        self, manifest_path: Path | None
    ) -> dict[str, Any] | None:
        if manifest_path is None or not manifest_path.exists():
            return None
        try:
            return read_manifest(manifest_path)
        except Exception:
            return None

    def _extract_dataset_versions(self, dataframe: pd.DataFrame) -> tuple[str, ...]:
        if "dataset_version" not in dataframe.columns:
            return ()

        versions = dataframe["dataset_version"].dropna().astype(str).map(str.strip)
        unique_versions = sorted({value for value in versions.tolist() if value})
        return tuple(unique_versions)

    def _validate_schema(self, dataframe: pd.DataFrame) -> tuple[bool, tuple[str, ...]]:
        result = validate_dataframe(dataframe)
        messages = tuple(issue.message for issue in result.issues)
        return bool(result.valid), messages

    def _build_dataset_file_metadata(
        self, dataset_path: Path | None
    ) -> _DatasetFileMetadata:
        if (
            dataset_path is None
            or not dataset_path.exists()
            or not dataset_path.is_file()
        ):
            return {"checksum": None, "size_bytes": None, "modified_at": None}

        stat = dataset_path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        return {
            "checksum": compute_file_sha256(dataset_path),
            "size_bytes": int(stat.st_size),
            "modified_at": modified_at,
        }

    def _build_category_summaries(
        self, dataframe: pd.DataFrame
    ) -> tuple[CategorySummary, ...]:
        required_columns = {CATEGORY_COLUMN, COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN}
        if dataframe.empty or not required_columns.issubset(dataframe.columns):
            return ()

        grouped = (
            dataframe.dropna(subset=[CATEGORY_COLUMN])
            .groupby(CATEGORY_COLUMN, dropna=True)
            .agg(
                row_count=(CATEGORY_COLUMN, "size"),
                country_count=(COUNTRY_CODE_COLUMN, "nunique"),
                metric_count=(METRIC_ID_COLUMN, "nunique"),
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

    def _extract_year_range(
        self, dataframe: pd.DataFrame
    ) -> tuple[int | None, int | None]:
        if dataframe.empty or YEAR_COLUMN not in dataframe.columns:
            return None, None

        numeric_years = (
            pd.to_numeric(dataframe[YEAR_COLUMN], errors="coerce").dropna().astype(int)
        )
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

    def _resolve_manifest_path(self, dataset_path: Path | None) -> Path | None:
        if dataset_path is None:
            return None
        return default_manifest_path_for_dataset(dataset_path).resolve()
