from __future__ import annotations

from pathlib import Path

from country_compare.config.loader import (
    load_configuration_bundle,
    load_metrics_config,
    load_scoring_config,
)
from country_compare.config.models import ConfigurationBundle, MetricsConfig, ScoringConfig
from country_compare.config.validator import (
    resolve_profile_options,
    resolve_profile_weights,
    validate_configuration_bundle,
    validate_metrics_against_dataframe,
)
from country_compare.services.app_context import AppContext
from country_compare.services.dataset_service import DatasetService
from country_compare.services.errors import AppError, error_from_exception
from country_compare.services.models import ConfigStatus, ProfileOption, ValidationReport


class ConfigService:
    """Framework-neutral configuration access and validation helpers."""

    def __init__(
        self,
        context: AppContext,
        *,
        dataset_service: DatasetService | None = None,
    ) -> None:
        self.context = context
        self.dataset_service = dataset_service

    def load_metrics_config(self) -> MetricsConfig:
        return load_metrics_config(self.context.metrics_config_path)

    def load_scoring_config(self) -> ScoringConfig:
        return load_scoring_config(self.context.scoring_config_path)

    def load_bundle(self, *, validate: bool = True) -> ConfigurationBundle:
        return load_configuration_bundle(
            self.context.metrics_config_path,
            self.context.scoring_config_path,
            validate=validate,
        )

    def validate_bundle(self, *, against_dataset: bool = False) -> ValidationReport:
        try:
            bundle = self.load_bundle(validate=False)
            validate_configuration_bundle(bundle)

            messages: list[str] = [
                "Configuration bundle loaded successfully.",
                "Configuration references and weight handling validated successfully.",
            ]

            if against_dataset:
                dataset = self._load_dataset_for_validation()
                validate_metrics_against_dataframe(bundle.metrics, dataset)
                messages.append("Metrics config is consistent with the current dataset.")

            return ValidationReport(valid=True, messages=tuple(messages))
        except Exception as exc:
            return ValidationReport(
                valid=False,
                messages=(str(exc),),
                error=error_from_exception(
                    exc,
                    default_title="Configuration error",
                    default_user_message="The project configuration could not be validated.",
                ),
            )

    def get_profile_summaries(self) -> tuple[ProfileOption, ...]:
        bundle = self.load_bundle(validate=True)

        options: list[ProfileOption] = []
        for profile_name, profile in sorted(bundle.scoring.profiles.items()):
            resolved_options = resolve_profile_options(bundle.scoring, profile_name)
            # Call resolve_profile_weights now so later UI/API layers can rely on the
            # fact that profile summaries were built from fully resolvable profiles.
            resolve_profile_weights(bundle.metrics, bundle.scoring, profile_name)
            options.append(
                ProfileOption(
                    name=profile_name,
                    metric_count=len(profile.metrics),
                    description=profile.description,
                    year_strategy=resolved_options["year_strategy"],
                    missing_data_policy=resolved_options["missing_data_policy"],
                )
            )

        return tuple(options)

    def get_status(self, *, validate_against_dataset: bool = False) -> ConfigStatus:
        metrics_path = self.context.metrics_config_path.resolve()
        scoring_path = self.context.scoring_config_path.resolve()
        metrics_exists = metrics_path.exists()
        scoring_exists = scoring_path.exists()

        if not metrics_exists or not scoring_exists:
            missing_paths: list[str] = []
            if not metrics_exists:
                missing_paths.append(str(metrics_path))
            if not scoring_exists:
                missing_paths.append(str(scoring_path))

            error = AppError(
                code="resource_not_found",
                title="Configuration file not found",
                user_message="One or more configuration files could not be found.",
                technical_detail="Missing configuration paths: " + ", ".join(missing_paths),
            )
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                validation=ValidationReport(valid=False, error=error, messages=(error.technical_detail or "",)),
                error=error,
            )

        validation = self.validate_bundle(against_dataset=validate_against_dataset)
        if not validation.valid:
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                bundle_loaded=False,
                validation=validation,
                error=validation.error,
            )

        try:
            bundle = self.load_bundle(validate=True)
            profiles = self.get_profile_summaries()
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                metrics_count=len(bundle.metrics.metrics),
                profile_count=len(bundle.scoring.profiles),
                default_profile=bundle.scoring.default_profile,
                profiles=profiles,
                bundle_loaded=True,
                validation=validation,
            )
        except Exception as exc:
            error = error_from_exception(
                exc,
                default_title="Configuration error",
                default_user_message="The configuration files could not be loaded for overview display.",
            )
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                bundle_loaded=False,
                validation=ValidationReport(valid=False, messages=(str(exc),), error=error),
                error=error,
            )

    def _load_dataset_for_validation(self):
        if self.dataset_service is None:
            dataset_service = DatasetService(self.context)
        else:
            dataset_service = self.dataset_service
        return dataset_service.load_dataframe()
