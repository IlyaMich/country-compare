"""Framework-neutral service/orchestration layer for UI, API, and notebooks."""

from country_compare.services.app_context import AppContext
from country_compare.services.config_service import ConfigService
from country_compare.services.dataset_service import DatasetService
from country_compare.services.errors import AppError, AppServiceError, error_from_exception
from country_compare.services.facade import AppFacade
from country_compare.services.results import AppMessage, ComparisonResult, PresentationResult
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.presentation_service import PresentationService
from country_compare.services.models import (
    AppStatus,
    CategorySummary,
    ConfigStatus,
    CountryOption,
    DatasetSummary,
    MetricOption,
    OverviewStatus,
    ProfileOption,
    ValidationReport,
)
from country_compare.services.requests import (
    BaseComparisonRequest,
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)

__all__ = [
    "AppContext",
    "AppError",
    "AppServiceError",
    "error_from_exception",
    "DatasetService",
    "ConfigService",
    "AppFacade",
    "AppStatus",
    "CountryOption",
    "MetricOption",
    "ProfileOption",
    "CategorySummary",
    "DatasetSummary",
    "ConfigStatus",
    "ValidationReport",
    "OverviewStatus",
    "AppMessage",
    "ComparisonResult",
    "PresentationResult",
    "ComparisonService",
    "PresentationService",
    "BaseComparisonRequest",
    "SingleMetricRequest",
    "MultiMetricRequest",
    "WeightedScoreRequest",
]