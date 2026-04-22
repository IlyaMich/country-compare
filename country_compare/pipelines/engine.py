from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, PRIMARY_KEY_COLUMNS, REQUIRED_COLUMNS
from country_compare.data.ingestion.registry import resolve_source_adapter
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.errors import (
    AdapterExecutionError,
    CanonicalValidationError,
    PipelineError,
    PublicationError,
)
from country_compare.pipelines.models import (
    ProcessingRequest,
    ProcessingResult,
    PublicationReport,
    RunMetadata,
    SourceProcessingResult,
    ValidationReport,
)
from country_compare.pipelines.publish import publish_dataframe


class PipelineEngine:
    def __init__(self, *, acquirer: DirectoryRawAcquirer | None = None) -> None:
        self.acquirer = acquirer or DirectoryRawAcquirer()

    def run(self, request: ProcessingRequest) -> ProcessingResult:
        started_at = datetime.now(tz=timezone.utc)
        run_metadata = RunMetadata(
            run_id=uuid4().hex,
            started_at=started_at,
            source_count=sum(1 for source in request.sources if source.enabled),
        )

        source_results: list[SourceProcessingResult] = []
        canonical_frames: list[pd.DataFrame] = []
        warnings: list[str] = []
        run_error: str | None = None
        validation_report: ValidationReport | None = None
        publication_report: PublicationReport | None = None
        metric_dataset: Any | None = None

        try:
            for source_spec in request.sources:
                if not source_spec.enabled:
                    continue

                source_result = self._process_source(source_spec, request=request)
                source_results.append(source_result)
                if source_result.ok and source_result.dataframe is not None:
                    canonical_frames.append(source_result.dataframe)
                else:
                    run_metadata.failed_source_count += 1
                    if source_result.error:
                        warnings.append(
                            f"source '{source_spec.source_id}' failed: {source_result.error}"
                        )
                    if request.stop_on_source_error:
                        raise PipelineError(
                            f"stopping on source error for '{source_spec.source_id}': "
                            f"{source_result.error or 'unknown source failure'}"
                        )

            run_metadata.successful_source_count = sum(1 for result in source_results if result.ok)

            if not canonical_frames:
                raise PipelineError("no valid canonical outputs were produced by the pipeline")

            merged = self._merge_frames(canonical_frames)
            validation_report, validated_dataframe, metric_dataset = self._validate_merged_dataframe(
                merged,
                request=request,
            )

            if not validation_report.ok:
                raise CanonicalValidationError(
                    "; ".join(validation_report.error_messages)
                    or "canonical dataframe validation failed"
                )

            if request.publish:
                publication_report = publish_dataframe(
                    validated_dataframe,
                    store=request.store,
                    write_metric_dataset=request.write_metric_dataset,
                )
            else:
                publication_report = PublicationReport(
                    attempted=False,
                    ok=True,
                    row_count=int(len(validated_dataframe.index)),
                )

            result = ProcessingResult(
                canonical_dataframe=validated_dataframe,
                metric_dataset=metric_dataset if request.write_metric_dataset else None,
                source_results=tuple(source_results),
                validation_report=validation_report,
                publication_report=publication_report,
                run_metadata=replace(
                    run_metadata,
                    finished_at=datetime.now(tz=timezone.utc),
                ),
                warnings=warnings,
            )
            return result

        except PublicationError as exc:
            run_error = str(exc)
        except Exception as exc:
            run_error = str(exc)

        if validation_report is None:
            validation_report = ValidationReport(
                ok=False,
                error_messages=[run_error or "pipeline failed before validation"],
            )
        if publication_report is None:
            publication_report = PublicationReport(
                attempted=request.publish,
                ok=False if request.publish else True,
                error=run_error if request.publish else None,
            )

        return ProcessingResult(
            canonical_dataframe=None,
            metric_dataset=None,
            source_results=tuple(source_results),
            validation_report=validation_report,
            publication_report=publication_report,
            run_metadata=replace(
                run_metadata,
                finished_at=datetime.now(tz=timezone.utc),
            ),
            warnings=warnings,
            error=run_error,
        )

    def _process_source(
        self,
        source_spec: Any,
        *,
        request: ProcessingRequest,
    ) -> SourceProcessingResult:
        try:
            assets = tuple(
                self.acquirer.acquire(source_spec, raw_root=self._resolve_raw_root(request.raw_root))
            )
            adapter = resolve_source_adapter(source_spec.adapter_id)
            dataframe = self._execute_adapter(adapter, assets, source_spec=source_spec)
            return SourceProcessingResult(
                source_id=source_spec.source_id,
                adapter_id=source_spec.adapter_id,
                ok=True,
                assets=assets,
                dataframe=dataframe,
                raw_row_count=int(len(dataframe.index)),
                canonical_row_count=int(len(dataframe.index)),
            )
        except Exception as exc:
            return SourceProcessingResult(
                source_id=source_spec.source_id,
                adapter_id=source_spec.adapter_id,
                ok=False,
                error=str(exc),
            )

    @staticmethod
    def _resolve_raw_root(raw_root: str | Path | None) -> Path | None:
        if raw_root is None:
            return None
        return Path(raw_root)

    @staticmethod
    def _execute_adapter(adapter: Any, assets: tuple[Any, ...], *, source_spec: Any) -> pd.DataFrame:
        try:
            if hasattr(adapter, "process"):
                dataframe = adapter.process(list(assets), source_spec=source_spec)
            elif len(assets) == 1 and hasattr(adapter, "adapt"):
                dataframe = adapter.adapt(assets[0], source_spec=source_spec)
            else:
                dataframe = adapter.to_standardized_dataframe()
        except Exception as exc:
            raise AdapterExecutionError(str(exc)) from exc

        if not isinstance(dataframe, pd.DataFrame):
            raise AdapterExecutionError("adapter did not return a pandas DataFrame")
        return dataframe.copy(deep=True)

    @staticmethod
    def _merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
        merged = pd.concat(frames, ignore_index=True)
        ordered_columns = [column for column in ALL_COLUMNS if column in merged.columns]
        remaining_columns = [column for column in merged.columns if column not in ordered_columns]
        return merged.loc[:, [*ordered_columns, *remaining_columns]].copy(deep=True)

    def _validate_merged_dataframe(
        self,
        dataframe: pd.DataFrame,
        *,
        request: ProcessingRequest,
    ) -> tuple[ValidationReport, pd.DataFrame, Any | None]:
        errors: list[str] = []
        warnings: list[str] = []
        config_checked = False
        metric_dataset: Any | None = None

        try:
            validated_dataframe, metric_dataset = self._prepare_dataframe_for_storage(dataframe)
        except Exception as exc:
            errors.append(str(exc))
            validated_dataframe = dataframe.copy(deep=True)

        if not errors and request.validate_against_config:
            config_checked = True
            metrics_config = request.metrics_config
            if metrics_config is None:
                warnings.append(
                    "Config validation was requested but no metrics_config was provided."
                )
            else:
                try:
                    from country_compare.config.validator import validate_metrics_against_dataframe

                    validate_metrics_against_dataframe(metrics_config, validated_dataframe)
                except Exception as exc:
                    errors.append(str(exc))

        report = ValidationReport(
            ok=not errors,
            error_messages=errors,
            warning_messages=warnings,
            validated_row_count=int(len(validated_dataframe.index)),
            config_checked=config_checked,
        )
        return report, validated_dataframe, metric_dataset

    @staticmethod
    def _prepare_dataframe_for_storage(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, Any | None]:
        from country_compare.data import validation as validation_module

        candidate = dataframe.copy(deep=True)

        for function_name in (
            "prepare_dataframe_for_storage",
            "canonicalize_and_validate_dataframe",
        ):
            function = getattr(validation_module, function_name, None)
            if function is None:
                continue
            result = function(candidate.copy(deep=True))
            extracted = _extract_dataframe(result)
            if extracted is not None:
                candidate = extracted.copy(deep=True)
                break

        dataset = None
        dataframe_to_metric_dataset = getattr(validation_module, "dataframe_to_metric_dataset", None)
        if callable(dataframe_to_metric_dataset):
            dataset = dataframe_to_metric_dataset(candidate)

        if dataset is None:
            _fallback_validate_dataframe(candidate)

        return candidate, dataset


def _extract_dataframe(result: Any) -> pd.DataFrame | None:
    if isinstance(result, pd.DataFrame):
        return result
    dataframe = getattr(result, "dataframe", None)
    if isinstance(dataframe, pd.DataFrame):
        return dataframe
    return None


def _fallback_validate_dataframe(dataframe: pd.DataFrame) -> None:
    missing_required = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing_required:
        raise CanonicalValidationError(
            f"dataframe is missing required canonical columns: {missing_required}"
        )

    duplicate_mask = dataframe.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)
    if duplicate_mask.any():
        duplicates = dataframe.loc[duplicate_mask, list(PRIMARY_KEY_COLUMNS)]
        raise CanonicalValidationError(
            "duplicate canonical primary-key rows detected: "
            f"{duplicates.to_dict(orient='records')}"
        )

    for column in REQUIRED_COLUMNS:
        if dataframe[column].isna().any():
            raise CanonicalValidationError(
                f"required column '{column}' contains missing values"
            )

    try:
        years = pd.to_numeric(dataframe["year"], errors="raise")
        if ((years < 1900) | (years > 2100)).any():
            raise CanonicalValidationError("year values must be between 1900 and 2100")
    except Exception as exc:
        if isinstance(exc, CanonicalValidationError):
            raise
        raise CanonicalValidationError("year column could not be validated as numeric") from exc

    try:
        values = pd.to_numeric(dataframe["value"], errors="raise")
        if values.isna().any():
            raise CanonicalValidationError("value column contains invalid numeric values")
    except Exception as exc:
        if isinstance(exc, CanonicalValidationError):
            raise
        raise CanonicalValidationError("value column could not be validated as numeric") from exc

    country_codes = dataframe["country_code"].astype("string").str.upper()
    invalid_country_codes = country_codes[country_codes.str.len() != 3]
    if not invalid_country_codes.empty:
        raise CanonicalValidationError(
            "country_code must contain ISO alpha-3 codes"
        )


def run_processing_pipeline(request: ProcessingRequest) -> ProcessingResult:
    return PipelineEngine().run(request)
