from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

from country_compare.config.loader import (
    load_configuration_bundle,
    load_metrics_config,
    load_scoring_config,
)
from country_compare.config.models import (
    ConfigurationBundle,
    MetricsConfig,
    ScoringConfig,
)
from country_compare.config.validator import (
    resolve_profile_options,
    resolve_profile_weights,
    validate_configuration_bundle,
    validate_metrics_against_dataframe,
)
from country_compare.services.app_context import AppContext
from country_compare.services.dataset_service import DatasetService
from country_compare.services.errors import AppError, error_from_exception
from country_compare.services.models import (
    ConfigStatus,
    ProfileOption,
    ValidationReport,
)


class ConfigService:
    """Framework-neutral configuration access, validation, and persistence helpers."""

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

    def load_bundle_data(self, *, validate: bool = False) -> dict[str, dict[str, Any]]:
        bundle = self.load_bundle(validate=validate)
        return self.export_bundle_data(bundle=bundle)

    def export_bundle_data(
        self,
        *,
        bundle: ConfigurationBundle,
        exclude_none: bool = True,
    ) -> dict[str, dict[str, Any]]:
        return {
            "metrics": bundle.metrics.model_dump(
                mode="json", exclude_none=exclude_none
            ),
            "scoring": bundle.scoring.model_dump(
                mode="json", exclude_none=exclude_none
            ),
        }

    def build_bundle_from_data(
        self,
        *,
        metrics_data: dict[str, Any],
        scoring_data: dict[str, Any],
        validate: bool = True,
    ) -> ConfigurationBundle:
        metrics_config = self._coerce_metrics_config(metrics_data)
        scoring_config = self._coerce_scoring_config(scoring_data)
        bundle = ConfigurationBundle(metrics=metrics_config, scoring=scoring_config)
        if validate:
            validate_configuration_bundle(bundle)
        return bundle

    def validate_bundle(self, *, against_dataset: bool = False) -> ValidationReport:
        try:
            bundle = self.load_bundle(validate=False)
            self._validate_loaded_bundle(bundle, against_dataset=against_dataset)
            messages = self._success_messages(against_dataset=against_dataset)
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

    def validate_bundle_data(
        self,
        *,
        metrics_data: dict[str, Any],
        scoring_data: dict[str, Any],
        against_dataset: bool = False,
    ) -> ValidationReport:
        try:
            bundle = self.build_bundle_from_data(
                metrics_data=metrics_data,
                scoring_data=scoring_data,
                validate=False,
            )
            self._validate_loaded_bundle(bundle, against_dataset=against_dataset)
            messages = self._success_messages(against_dataset=against_dataset)
            return ValidationReport(valid=True, messages=tuple(messages))
        except Exception as exc:
            return ValidationReport(
                valid=False,
                messages=(str(exc),),
                error=error_from_exception(
                    exc,
                    default_title="Configuration error",
                    default_user_message="The project configuration draft could not be validated.",
                ),
            )

    def save_metrics_config(
        self, metrics_config: MetricsConfig | dict[str, Any]
    ) -> None:
        resolved = self._coerce_metrics_config(metrics_config)
        payload = resolved.model_dump(mode="json", exclude_none=True)
        self._write_yaml_atomic(self.context.metrics_config_path, payload)

    def save_scoring_config(
        self, scoring_config: ScoringConfig | dict[str, Any]
    ) -> None:
        resolved = self._coerce_scoring_config(scoring_config)
        payload = resolved.model_dump(mode="json", exclude_none=True)
        self._write_yaml_atomic(self.context.scoring_config_path, payload)

    def save_bundle(self, bundle: ConfigurationBundle) -> None:
        validate_configuration_bundle(bundle)
        metrics_payload = bundle.metrics.model_dump(mode="json", exclude_none=True)
        scoring_payload = bundle.scoring.model_dump(mode="json", exclude_none=True)
        self._write_bundle_atomic(
            metrics_payload=metrics_payload, scoring_payload=scoring_payload
        )

    def save_bundle_data(
        self,
        *,
        metrics_data: dict[str, Any],
        scoring_data: dict[str, Any],
        validate_against_dataset: bool = False,
    ) -> ValidationReport:
        validation = self.validate_bundle_data(
            metrics_data=metrics_data,
            scoring_data=scoring_data,
            against_dataset=validate_against_dataset,
        )
        if not validation.valid:
            return validation

        try:
            bundle = self.build_bundle_from_data(
                metrics_data=metrics_data,
                scoring_data=scoring_data,
                validate=True,
            )
            self.save_bundle(bundle)
            return validation
        except Exception as exc:
            return ValidationReport(
                valid=False,
                messages=(str(exc),),
                error=error_from_exception(
                    exc,
                    default_title="Save failed",
                    default_user_message="The validated configuration could not be saved.",
                ),
            )

    def get_profile_summaries(self) -> tuple[ProfileOption, ...]:
        bundle = self.load_bundle(validate=True)

        options: list[ProfileOption] = []
        for profile_name, profile in sorted(bundle.scoring.profiles.items()):
            resolved_options = resolve_profile_options(bundle.scoring, profile_name)
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
                technical_detail="Missing configuration paths: "
                + ", ".join(missing_paths),
            )
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                validation=ValidationReport(
                    valid=False, error=error, messages=(error.technical_detail or "",)
                ),
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
                default_user_message=(
                    "The configuration files could not be loaded for overview display."
                ),
            )
            return ConfigStatus(
                metrics_config_path=str(metrics_path),
                scoring_config_path=str(scoring_path),
                metrics_config_exists=metrics_exists,
                scoring_config_exists=scoring_exists,
                bundle_loaded=False,
                validation=ValidationReport(
                    valid=False, messages=(str(exc),), error=error
                ),
                error=error,
            )

    def _coerce_metrics_config(
        self, metrics_config: MetricsConfig | dict[str, Any]
    ) -> MetricsConfig:
        if isinstance(metrics_config, MetricsConfig):
            return metrics_config
        return MetricsConfig.model_validate(metrics_config)

    def _coerce_scoring_config(
        self, scoring_config: ScoringConfig | dict[str, Any]
    ) -> ScoringConfig:
        if isinstance(scoring_config, ScoringConfig):
            return scoring_config
        return ScoringConfig.model_validate(scoring_config)

    def _validate_loaded_bundle(
        self,
        bundle: ConfigurationBundle,
        *,
        against_dataset: bool,
    ) -> None:
        validate_configuration_bundle(bundle)
        if against_dataset:
            dataset = self._load_dataset_for_validation()
            validate_metrics_against_dataframe(bundle.metrics, dataset)

    def _success_messages(self, *, against_dataset: bool) -> list[str]:
        messages = [
            "Configuration bundle loaded successfully.",
            "Configuration references and weight handling validated successfully.",
        ]
        if against_dataset:
            messages.append("Metrics config is consistent with the current dataset.")
        return messages

    def _load_dataset_for_validation(self):
        if self.dataset_service is None:
            dataset_service = DatasetService(self.context)
        else:
            dataset_service = self.dataset_service
        return dataset_service.load_dataframe()

    def _write_bundle_atomic(
        self,
        *,
        metrics_payload: dict[str, Any],
        scoring_payload: dict[str, Any],
    ) -> None:
        metrics_path = self.context.metrics_config_path
        scoring_path = self.context.scoring_config_path
        metrics_temp = self._write_yaml_temp(metrics_path, metrics_payload)
        scoring_temp = self._write_yaml_temp(scoring_path, scoring_payload)
        try:
            os.replace(metrics_temp, metrics_path)
            os.replace(scoring_temp, scoring_path)
        except Exception:
            for temp_path in (metrics_temp, scoring_temp):
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
            raise

    def _write_yaml_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        temp_path = self._write_yaml_temp(path, payload)
        try:
            os.replace(temp_path, path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

    def _write_yaml_temp(self, path: Path, payload: dict[str, Any]) -> Path:
        resolved_path = Path(path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            prefix=resolved_path.name + ".",
            dir=resolved_path.parent,
            delete=False,
        ) as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
            temp_path = Path(handle.name)
        return temp_path
