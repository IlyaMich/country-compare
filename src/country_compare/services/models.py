from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from country_compare.services.errors import AppError


@dataclass(frozen=True)
class CountryOption:
    code: str
    name: str


@dataclass(frozen=True)
class MetricOption:
    metric_id: str
    display_name: str
    category: str | None = None
    unit: str | None = None


@dataclass(frozen=True)
class ProfileOption:
    name: str
    metric_count: int
    description: str | None = None
    year_strategy: str | None = None
    missing_data_policy: str | None = None


@dataclass(frozen=True)
class CategorySummary:
    name: str
    row_count: int
    country_count: int
    metric_count: int


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    messages: tuple[str, ...] = ()
    error: AppError | None = None


@dataclass(frozen=True)
class DatasetSummary:
    exists: bool
    backend: str
    dataset_path: str | None = None
    row_count: int = 0
    country_count: int = 0
    metric_count: int = 0
    year_min: int | None = None
    year_max: int | None = None
    available_columns: tuple[str, ...] = ()
    categories: tuple[CategorySummary, ...] = ()
    dataset_versions: tuple[str, ...] = ()
    dataset_checksum: str | None = None
    dataset_size_bytes: int | None = None
    dataset_modified_at: str | None = None
    schema_valid: bool | None = None
    schema_issue_count: int = 0
    schema_issues: tuple[str, ...] = ()
    error: AppError | None = None


@dataclass(frozen=True)
class ConfigStatus:
    metrics_config_path: str
    scoring_config_path: str
    metrics_config_exists: bool
    scoring_config_exists: bool
    metrics_count: int = 0
    profile_count: int = 0
    default_profile: str | None = None
    profiles: tuple[ProfileOption, ...] = ()
    bundle_loaded: bool = False
    validation: ValidationReport = field(
        default_factory=lambda: ValidationReport(valid=False)
    )
    error: AppError | None = None


@dataclass(frozen=True)
class OverviewStatus:
    dataset: DatasetSummary
    config: ConfigStatus
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.dataset.exists and self.config.validation.valid


@dataclass(frozen=True)
class AppStatus:
    ready: bool
    context: dict[str, Any]
    error: AppError | None = None
