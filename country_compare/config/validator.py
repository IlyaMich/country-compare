from __future__ import annotations

import pandas as pd

from country_compare.config.models import (
    ConfigurationBundle,
    MetricsConfig,
    ScoringConfig,
    WeightHandlingStrategy,
)
from country_compare.data.contract import METRIC_ID_COLUMN


class ConfigurationValidationError(ValueError):
    """Raised when configuration is internally inconsistent."""


def validate_configuration_bundle(bundle: ConfigurationBundle) -> None:
    validate_scoring_references(bundle.metrics, bundle.scoring)
    validate_weight_handling(bundle.metrics, bundle.scoring)


def validate_scoring_references(metrics: MetricsConfig, scoring: ScoringConfig) -> None:
    known_metric_ids = set(metrics.metrics.keys())

    for profile_name, _profile in scoring.profiles.items():
        unknown_profile_metrics = set(_profile.metrics) - known_metric_ids
        if unknown_profile_metrics:
            unknown = ", ".join(sorted(unknown_profile_metrics))
            raise ConfigurationValidationError(
                f"profile '{profile_name}' references undefined metrics: {unknown}"
            )

        unknown_weight_metrics = set(_profile.weights.keys()) - set(_profile.metrics)
        if unknown_weight_metrics:
            unknown = ", ".join(sorted(unknown_weight_metrics))
            raise ConfigurationValidationError(
                f"profile '{profile_name}' defines weights for metrics not included "
                f"in its metrics list: {unknown}"
            )

        unknown_override_metrics = set(_profile.normalization_overrides.keys()) - set(
            _profile.metrics
        )
        if unknown_override_metrics:
            unknown = ", ".join(sorted(unknown_override_metrics))
            raise ConfigurationValidationError(
                f"profile '{profile_name}' defines normalization overrides for metrics "
                f"not included in its metrics list: {unknown}"
            )


def validate_weight_handling(metrics: MetricsConfig, scoring: ScoringConfig) -> None:
    if scoring.weight_handling != WeightHandlingStrategy.REQUIRE_SUM_TO_ONE:
        return

    for profile_name, _profile in scoring.profiles.items():
        resolved = resolve_profile_weights(metrics, scoring, profile_name)
        total = sum(resolved.values())
        if abs(total - 1.0) > 1e-9:
            raise ConfigurationValidationError(
                f"profile '{profile_name}' resolved weights must sum to 1.0, got {total}"
            )


def resolve_profile_weights(
    metrics: MetricsConfig,
    scoring: ScoringConfig,
    profile_name: str,
) -> dict[str, float]:
    if profile_name not in scoring.profiles:
        raise ConfigurationValidationError(f"unknown scoring profile: {profile_name}")

    profile = scoring.profiles[profile_name]

    raw_weights: dict[str, float] = {}
    for metric_id in profile.metrics:
        if metric_id in profile.weights:
            raw_weights[metric_id] = profile.weights[metric_id]
        else:
            raw_weights[metric_id] = metrics.metrics[metric_id].default_weight

    total = sum(raw_weights.values())
    if total <= 0:
        raise ConfigurationValidationError(
            f"profile '{profile_name}' resolved to a non-positive total weight"
        )

    if scoring.weight_handling == WeightHandlingStrategy.REQUIRE_SUM_TO_ONE:
        return raw_weights

    return {metric_id: weight / total for metric_id, weight in raw_weights.items()}


def validate_metrics_against_dataframe(
    metrics: MetricsConfig,
    dataframe: pd.DataFrame,
) -> None:
    """
    Optional consistency check against canonical dataset rows.

    Precedence strategy:
    - Config is authoritative for comparison behavior.
    - Dataset remains authoritative for actual observed rows.
    - Contradictions in shared metadata are treated as validation errors.

    Expected dataset columns when present:
    - metric_id
    - category
    - unit
    - higher_is_better
    """
    required_cols = {"metric_id"}
    missing_required = required_cols - set(dataframe.columns)
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ConfigurationValidationError(
            f"dataframe is missing required columns for config validation: {missing}"
        )

    if dataframe.empty:
        return

    known_metric_ids = set(metrics.metrics.keys())
    dataset_metric_ids = set(dataframe["metric_id"].dropna().astype(str).unique())

    undefined_in_config = dataset_metric_ids - known_metric_ids
    if undefined_in_config:
        missing = ", ".join(sorted(undefined_in_config))
        raise ConfigurationValidationError(
            f"dataset contains metric_ids not defined in config: {missing}"
        )

    shared_fields = [
        field
        for field in ["category", "unit", "higher_is_better"]
        if field in dataframe.columns
    ]

    if not shared_fields:
        return

    deduped = (
        dataframe[["metric_id", *shared_fields]].dropna(subset=["metric_id"]).copy()
    )

    for metric_id, metric_df in deduped.groupby(METRIC_ID_COLUMN):
        metric_cfg = metrics.metrics[str(metric_id)]

        for field in shared_fields:
            observed_values = {
                _normalize_scalar(value)
                for value in metric_df[field].dropna().unique().tolist()
            }
            if not observed_values:
                continue

            expected_value = _normalize_scalar(getattr(metric_cfg, field))
            if expected_value is None:
                continue

            if observed_values != {expected_value}:
                raise ConfigurationValidationError(
                    f"metric '{metric_id}' has conflicting '{field}' values. "
                    f"Config={expected_value!r}, dataset={sorted(observed_values)!r}"
                )


def resolve_profile_options(
    scoring: ScoringConfig,
    profile_name: str,
) -> dict[str, str]:
    if profile_name not in scoring.profiles:
        raise ConfigurationValidationError(f"unknown scoring profile: {profile_name}")

    profile = scoring.profiles[profile_name]

    year_strategy = profile.year_strategy or scoring.default_year_strategy
    missing_data_policy = (
        profile.missing_data_policy or scoring.default_missing_data_policy
    )

    return {
        "year_strategy": year_strategy.value,
        "missing_data_policy": missing_data_policy.value,
    }


def _normalize_scalar(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value
