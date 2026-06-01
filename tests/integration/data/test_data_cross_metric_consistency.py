from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_metric_ids_have_unique_metric_names(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    metric_name_to_ids: dict[str, set[str]] = {}

    for metric_id, group in dataframe.groupby("metric_id"):
        metric_name = str(group["metric_name"].dropna().iloc[0])
        metric_name_to_ids.setdefault(metric_name, set()).add(str(metric_id))

    duplicates = {
        metric_name: sorted(metric_ids)
        for metric_name, metric_ids in metric_name_to_ids.items()
        if len(metric_ids) > 1
    }

    assert duplicates == {}


def test_metric_ids_do_not_share_the_same_source_url_and_unit_with_same_name(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    signatures: dict[tuple[str, str, str], set[str]] = {}

    for metric_id, group in dataframe.groupby("metric_id"):
        metric_name = str(group["metric_name"].dropna().iloc[0])
        unit = str(group["unit"].dropna().iloc[0])
        source_url = str(group["source_url"].dropna().iloc[0])
        signatures.setdefault((metric_name, unit, source_url), set()).add(
            str(metric_id)
        )

    duplicate_signatures = {
        signature: sorted(metric_ids)
        for signature, metric_ids in signatures.items()
        if len(metric_ids) > 1
    }

    assert duplicate_signatures == {}


def test_country_codes_map_to_consistent_country_names(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    inconsistent: list[dict[str, object]] = []

    for country_code, group in dataframe.groupby("country_code", dropna=False):
        country_names = sorted(
            group["country_name"].dropna().astype(str).unique().tolist()
        )
        if len(country_names) != 1:
            inconsistent.append(
                {
                    "country_code": country_code,
                    "country_names": country_names,
                }
            )

    assert inconsistent == []


def test_no_two_metrics_have_identical_complete_value_series(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    series_by_metric: dict[str, tuple[tuple[str, int, float], ...]] = {}

    for metric_id, group in dataframe.groupby("metric_id"):
        records = tuple(
            sorted(
                (
                    str(row.country_code),
                    int(row.year),
                    round(float(row.value), 8),
                )
                for row in group.itertuples(index=False)
            )
        )
        series_by_metric[str(metric_id)] = records

    duplicate_pairs: list[tuple[str, str]] = []
    metric_ids = sorted(series_by_metric)

    for index, metric_id in enumerate(metric_ids):
        for other_metric_id in metric_ids[index + 1 :]:
            if series_by_metric[metric_id] == series_by_metric[other_metric_id]:
                duplicate_pairs.append((metric_id, other_metric_id))

    assert duplicate_pairs == []
