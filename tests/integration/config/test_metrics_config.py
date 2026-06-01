from __future__ import annotations

import re

import pytest

from country_compare.config.loader import load_metrics_config
from country_compare.paths import METRICS_CONFIG_PATH

pytestmark = pytest.mark.integration

METRIC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def test_metric_ids_are_stable_machine_readable_ids() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    invalid_metric_ids = [
        metric_id
        for metric_id in config.metrics
        if not METRIC_ID_PATTERN.fullmatch(metric_id)
    ]

    assert invalid_metric_ids == []


def test_metric_config_required_fields_are_populated() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    failures: list[dict[str, object]] = []

    for metric_id, metric in config.metrics.items():
        if not metric.display_name.strip():
            failures.append({"metric_id": metric_id, "field": "display_name"})

        if not metric.category.strip():
            failures.append({"metric_id": metric_id, "field": "category"})

        if metric.default_weight <= 0:
            failures.append(
                {
                    "metric_id": metric_id,
                    "field": "default_weight",
                    "value": metric.default_weight,
                }
            )

        if metric.unit is None or not metric.unit.strip():
            failures.append({"metric_id": metric_id, "field": "unit"})

        if metric.source is None or not metric.source.strip():
            failures.append({"metric_id": metric_id, "field": "source"})

    assert failures == []


def test_metric_display_names_are_unique() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    display_name_to_metric_ids: dict[str, list[str]] = {}

    for metric_id, metric in config.metrics.items():
        display_name_to_metric_ids.setdefault(metric.display_name, []).append(metric_id)

    duplicates = {
        display_name: metric_ids
        for display_name, metric_ids in display_name_to_metric_ids.items()
        if len(metric_ids) > 1
    }

    assert duplicates == {}


def test_metric_units_and_categories_are_not_overly_fragmented() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    units = {metric.unit for metric in config.metrics.values()}
    categories = {metric.category for metric in config.metrics.values()}

    assert None not in units
    assert "" not in units
    assert "" not in categories
    assert len(units) >= 3
    assert len(categories) >= 3


def test_metric_higher_is_better_is_boolean() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    failures = [
        {"metric_id": metric_id, "higher_is_better": metric.higher_is_better}
        for metric_id, metric in config.metrics.items()
        if not isinstance(metric.higher_is_better, bool)
    ]

    assert failures == []


def test_metric_normalization_methods_are_declared() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    failures = [
        {"metric_id": metric_id}
        for metric_id, metric in config.metrics.items()
        if metric.normalization_method is None
    ]

    assert failures == []
