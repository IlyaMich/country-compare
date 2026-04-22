from __future__ import annotations

from country_compare.services.app_context import AppContext
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.config_service import ConfigService
from country_compare.services.dataset_service import DatasetService
from country_compare.services.models import OverviewStatus
from country_compare.services.presentation_service import PresentationService
from country_compare.services.serialization import serialize_overview_status


class AppFacade:
    """Small application facade for thin UI entrypoints."""

    def __init__(self, context: AppContext) -> None:
        self.context = context
        self.dataset = DatasetService(context)
        self.config = ConfigService(context, dataset_service=self.dataset)
        self.comparison = ComparisonService(
            context=context,
            dataset_service=self.dataset,
            config_service=self.config,
        )
        self.presentation = PresentationService()

    def get_overview_status(self, *, validate_config_against_dataset: bool = False) -> OverviewStatus:
        dataset_summary = self.dataset.get_dataset_summary()
        config_status = self.config.get_status(
            validate_against_dataset=validate_config_against_dataset and dataset_summary.exists
        )

        warnings: list[str] = []
        if not dataset_summary.exists:
            warnings.append("No dataset is currently available, so comparison pages cannot run yet.")
        if not config_status.validation.valid:
            warnings.append("Configuration is not currently valid, so scoring/comparison flows should remain disabled.")
        if dataset_summary.exists and not validate_config_against_dataset:
            warnings.append("Dataset-aware config validation is currently skipped. Enable it from the overview page when needed.")

        return OverviewStatus(
            dataset=dataset_summary,
            config=config_status,
            warnings=tuple(warnings),
        )

    def get_overview_status_payload(self, *, validate_config_against_dataset: bool = False) -> dict:
        status = self.get_overview_status(
            validate_config_against_dataset=validate_config_against_dataset,
        )
        return serialize_overview_status(status)

    def compare_single_metric(self, request):
        result = self.comparison.run_single_metric(request)
        return result, self.presentation.build_single_metric_presentation(result)

    def compare_multi_metric(self, request):
        result = self.comparison.run_multi_metric(request)
        return result, self.presentation.build_multi_metric_presentation(result)

    def compare_weighted_score(self, request):
        result = self.comparison.run_weighted_score(request)
        return result, self.presentation.build_weighted_score_presentation(result)
