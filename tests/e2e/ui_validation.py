from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlencode
import json
from io import BytesIO

import httpx
import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

UI_BASE_URL = os.getenv(
    "COUNTRY_COMPARE_E2E_UI_URL",
    "http://127.0.0.1:8501",
)

API_BASE_URL = os.getenv(
    "COUNTRY_COMPARE_E2E_API_URL",
    "http://127.0.0.1:8000",
)

API_KEY = os.getenv("COUNTRY_COMPARE_E2E_API_KEY", "")

_FORECAST_UI_PREFERRED_COLUMNS = (
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    "forecast_year",
    "forecast_horizon",
    "predicted_value",
    "unit",
    "prediction_method",
    "forecast_origin_year",
    "confidence_lower",
    "confidence_upper",
    "scenario_id",
    "diagnostic_status",
)

_PREDICTION_RUN_SPECIFIC_COLUMNS = (
    "prediction_run_id",
    "prediction_created_at",
)


def _csv_without_columns(
    payload: bytes,
    columns: tuple[str, ...],
) -> bytes:
    dataframe = pd.read_csv(
        BytesIO(payload),
        dtype=str,
        keep_default_na=False,
    )

    removable = [
        column
        for column in columns
        if column in dataframe.columns
    ]

    dataframe = dataframe.drop(columns=removable)

    return dataframe.to_csv(
        index=False,
        lineterminator="\n",
    ).encode("utf-8")


def _assert_prediction_run_metadata(
    payload: bytes,
) -> None:
    dataframe = pd.read_csv(
        BytesIO(payload),
        dtype=str,
        keep_default_na=False,
    )

    assert "prediction_run_id" in dataframe.columns
    assert "prediction_created_at" in dataframe.columns

    run_ids = dataframe["prediction_run_id"]
    created_at_values = dataframe["prediction_created_at"]

    assert run_ids.ne("").all()
    assert created_at_values.ne("").all()

    # Every row in this exported result must belong to one run.
    assert run_ids.nunique() == 1
    assert created_at_values.nunique() == 1

    parsed_created_at = pd.to_datetime(
        created_at_values.iloc[0],
        utc=True,
        errors="raise",
    )

    assert not pd.isna(parsed_created_at)


def _find_single_forecast_reference_case(
) -> tuple[
    str,
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    horizon_years = 3

    countries_payload = _api_get_json(
        "/api/v1/metadata/countries"
    )
    metrics_payload = _api_get_json(
        "/api/v1/metadata/metrics"
    )

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(item.get("code") or item.get("country_code") or "")
        .strip()
        .upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "")
        .strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [
        value for value in country_codes if value
    ]
    metric_ids = [
        value for value in metric_ids if value
    ]

    for metric_id in metric_ids:
        for country_code in country_codes:
            status_code, envelope = _api_post_json(
                "/api/v1/prediction/single-metric",
                {
                    "country_codes": [country_code],
                    "metric_id": metric_id,
                    "horizon_years": horizon_years,
                    "method": method,
                    "fallback_method": "last_observed",
                    "scenario_id": "baseline",
                },
            )

            if status_code != 200:
                continue

            if envelope.get("ok") is not True:
                continue

            try:
                forecast = _named_table_dataframe(
                    envelope,
                    "forecast",
                )
                diagnostics = (
                    _prediction_diagnostic_items(
                        envelope
                    )
                )
            except AssertionError:
                continue

            if len(forecast.index) != horizon_years:
                continue

            if len(diagnostics) != 1:
                continue

            diagnostic = diagnostics[0]

            if (
                diagnostic.get("country_code")
                != country_code
            ):
                continue

            if diagnostic.get("metric_id") != metric_id:
                continue

            if (
                diagnostic.get("method_requested")
                != method
            ):
                continue

            if diagnostic.get("method_used") != method:
                continue

            if diagnostic.get("fallback_used") is not False:
                continue

            return (
                country_code,
                metric_id,
                method,
                horizon_years,
                envelope,
            )

    pytest.fail(
        "Could not find a release-dataset series suitable "
        "for the deterministic UI-06 forecast reference case."
    )


def _find_multi_country_forecast_reference_case(
) -> tuple[
    list[str],
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    horizon_years = 3

    countries_payload = _api_get_json(
        "/api/v1/metadata/countries"
    )
    metrics_payload = _api_get_json(
        "/api/v1/metadata/metrics"
    )

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(
            item.get("code")
            or item.get("country_code")
            or ""
        )
        .strip()
        .upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(
            item.get("metric_id")
            or item.get("id")
            or ""
        ).strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [
        value
        for value in country_codes
        if value
    ]
    metric_ids = [
        value
        for value in metric_ids
        if value
    ]

    for metric_id in metric_ids:
        successful_countries: list[str] = []

        for country_code in country_codes:
            status_code, single_envelope = _api_post_json(
                "/api/v1/prediction/single-metric",
                {
                    "country_codes": [country_code],
                    "metric_id": metric_id,
                    "horizon_years": horizon_years,
                    "method": method,
                    "fallback_method": "last_observed",
                    "scenario_id": "baseline",
                },
            )

            if status_code != 200:
                continue

            if single_envelope.get("ok") is not True:
                continue

            try:
                forecast = _named_table_dataframe(
                    single_envelope,
                    "forecast",
                )
                diagnostics = (
                    _prediction_diagnostic_items(
                        single_envelope
                    )
                )
            except AssertionError:
                continue

            if len(forecast.index) != horizon_years:
                continue

            if len(diagnostics) != 1:
                continue

            diagnostic = diagnostics[0]

            if (
                diagnostic.get("country_code")
                != country_code
            ):
                continue

            if diagnostic.get("metric_id") != metric_id:
                continue

            if (
                diagnostic.get("method_requested")
                != method
            ):
                continue

            if diagnostic.get("method_used") != method:
                continue

            if diagnostic.get("fallback_used") is not False:
                continue

            successful_countries.append(country_code)

            if len(successful_countries) < 2:
                continue

            selected_countries = successful_countries[:2]

            status_code, batch_envelope = _api_post_json(
                "/api/v1/prediction/single-metric",
                {
                    "country_codes": selected_countries,
                    "metric_id": metric_id,
                    "horizon_years": horizon_years,
                    "method": method,
                    "fallback_method": "last_observed",
                    "fail_fast": False,
                    "scenario_id": "baseline",
                },
            )

            if status_code != 200:
                continue

            if batch_envelope.get("ok") is not True:
                continue

            try:
                batch_forecast = _named_table_dataframe(
                    batch_envelope,
                    "forecast",
                )
                batch_diagnostics = (
                    _prediction_diagnostic_items(
                        batch_envelope
                    )
                )
            except AssertionError:
                continue

            if (
                len(batch_forecast.index)
                != len(selected_countries)
                * horizon_years
            ):
                continue

            if len(batch_diagnostics) != len(
                selected_countries
            ):
                continue

            forecast_country_codes = set(
                batch_forecast["country_code"]
                .astype(str)
                .tolist()
            )

            if forecast_country_codes != set(
                selected_countries
            ):
                continue

            diagnostics_by_country = {
                str(item.get("country_code")): item
                for item in batch_diagnostics
            }

            if set(diagnostics_by_country) != set(
                selected_countries
            ):
                continue

            valid = True

            for code in selected_countries:
                diagnostic = diagnostics_by_country[code]

                if diagnostic.get("metric_id") != metric_id:
                    valid = False
                    break

                if (
                    diagnostic.get("method_requested")
                    != method
                ):
                    valid = False
                    break

                if diagnostic.get("method_used") != method:
                    valid = False
                    break

                if (
                    diagnostic.get("fallback_used")
                    is not False
                ):
                    valid = False
                    break

            if not valid:
                continue

            return (
                selected_countries,
                metric_id,
                method,
                horizon_years,
                batch_envelope,
            )

    pytest.fail(
        "Could not find two release-dataset countries "
        "suitable for the deterministic UI-07 "
        "multi-country forecast reference case."
    )


def _prediction_diagnostics_by_country(
    diagnostics: dict[str, object],
) -> dict[str, dict[str, object]]:
    items = diagnostics.get("items")
    assert isinstance(items, list)

    result: dict[str, dict[str, object]] = {}

    for item in items:
        assert isinstance(item, dict)

        country_code = item.get("country_code")
        assert isinstance(country_code, str)
        assert country_code

        assert country_code not in result
        result[country_code] = dict(item)

    return result


def _expected_forecast_ui_table(
    envelope: dict[str, object],
) -> pd.DataFrame:
    dataframe = _named_table_dataframe(
        envelope,
        "forecast",
    ).copy()

    if "row_type" in dataframe.columns:
        dataframe = dataframe.loc[
            dataframe["row_type"]
            .astype("string")
            .eq("predicted")
        ].copy()

    assert "year" in dataframe.columns
    assert "value" in dataframe.columns

    dataframe["forecast_year"] = pd.to_numeric(
        dataframe["year"],
        errors="coerce",
    ).astype("Int64")

    dataframe["predicted_value"] = pd.to_numeric(
        dataframe["value"],
        errors="coerce",
    ).astype("float64")

    for column in _FORECAST_UI_PREFERRED_COLUMNS:
        if column in dataframe.columns:
            continue

        if column in {
            "forecast_year",
            "forecast_horizon",
            "forecast_origin_year",
        }:
            dataframe[column] = pd.Series(
                pd.NA,
                index=dataframe.index,
                dtype="Int64",
            )
        elif column in {
            "predicted_value",
            "confidence_lower",
            "confidence_upper",
        }:
            dataframe[column] = pd.Series(
                float("nan"),
                index=dataframe.index,
                dtype="float64",
            )
        else:
            dataframe[column] = pd.NA

    sort_columns = [
        column
        for column in (
            "country_code",
            "metric_id",
            "forecast_year",
            "forecast_horizon",
        )
        if column in dataframe.columns
    ]

    if sort_columns:
        dataframe = dataframe.sort_values(
            sort_columns,
            kind="mergesort",
            na_position="last",
        )

    dataframe = dataframe.reset_index(drop=True)

    extras = [
        column
        for column in dataframe.columns
        if column not in _FORECAST_UI_PREFERRED_COLUMNS
    ]

    return dataframe.loc[
        :,
        [
            *_FORECAST_UI_PREFERRED_COLUMNS,
            *extras,
        ],
    ]


def _named_table_dataframe(
    envelope: dict[str, object],
    table_name: str,
) -> pd.DataFrame:
    tables = envelope.get("tables")
    assert isinstance(tables, dict)

    table = tables.get(table_name)
    assert isinstance(table, dict)

    columns = table.get("columns")
    records = table.get("records")

    assert isinstance(columns, list)
    assert isinstance(records, list)

    return pd.DataFrame(
        records,
        columns=[str(column) for column in columns],
    )


def _prediction_diagnostic_items(
    envelope: dict[str, object],
) -> list[dict[str, object]]:
    summary = envelope.get("summary")
    assert isinstance(summary, dict)

    diagnostics = summary.get("diagnostics")
    assert isinstance(diagnostics, dict)

    items = diagnostics.get("items")
    assert isinstance(items, list)

    result: list[dict[str, object]] = []

    for item in items:
        assert isinstance(item, dict)
        result.append(dict(item))

    return result


def _prediction_url(
    *,
    mode: str,
    method: str,
    metric: str,
    horizon_years: int | None = None,
    holdout_years: int | None = None,
    country: str | None = None,
    countries: list[str] | None = None,
) -> str:
    params: dict[str, str] = {
        "page": "Prediction",
        "prediction_mode": mode,
        "prediction_method": method,
        "prediction_metric": metric,
    }

    if country is not None:
        params["prediction_country"] = country

    if countries:
        params["prediction_countries"] = ",".join(countries)

    if horizon_years is not None:
        params["prediction_horizon_years"] = str(horizon_years)

    if holdout_years is not None:
        params["prediction_holdout_years"] = str(holdout_years)

    return f"{UI_BASE_URL}/?{urlencode(params)}"


def _select_prediction_tab(
    page: Page,
    tab_name: str,
) -> None:
    tab = page.get_by_role(
        "tab",
        name=tab_name,
        exact=True,
    )

    expect(tab).to_be_visible(timeout=20_000)
    tab.click()

    expect(tab).to_have_attribute(
        "aria-selected",
        "true",
        timeout=20_000,
    )


def _download_diagnostics_json(
    page: Page,
) -> dict[str, object]:
    download_button = page.get_by_role(
        "button",
        name="Download diagnostics JSON",
        exact=True,
    )

    expect(download_button).to_be_visible(
        timeout=20_000
    )

    with page.expect_download(timeout=20_000) as download_info:
        download_button.click()

    download_path = download_info.value.path()
    assert isinstance(download_path, Path)

    payload = json.loads(
        download_path.read_text(encoding="utf-8")
    )

    assert isinstance(payload, dict)
    return payload


def _select_sidebar_page(
    page: Page,
    label: str,
) -> None:
    sidebar = page.locator('[data-testid="stSidebarContent"]')

    radio = sidebar.get_by_role(
        "radio",
        name=label,
        exact=True,
    )

    expect(radio).to_be_visible()

    radio_label = radio.locator("xpath=ancestor::label[1]")

    expect(radio_label).to_be_visible()

    radio_label.click()

    expect(radio).to_be_checked(timeout=20_000)


def _main_table_dataframe(
    envelope: dict[str, object],
) -> pd.DataFrame:
    tables = envelope.get("tables")

    assert isinstance(tables, dict)

    main = tables.get("main")

    assert isinstance(main, dict)

    columns = main.get("columns")
    records = main.get("records")

    assert isinstance(columns, list)
    assert isinstance(records, list)

    return pd.DataFrame(
        records,
        columns=[str(column) for column in columns],
    )


def _csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(
        index=False,
        lineterminator="\n",
    ).encode("utf-8")


def _expected_multi_metric_ui_table(
    api_table: pd.DataFrame,
) -> pd.DataFrame:
    presentation_columns = [
        "metric_id",
        "metric_name",
        "country_code",
        "country_name",
        "value",
        "normalized_value",
        "rank",
        "year",
        "unit",
        "category",
        "normalization_method",
        "normalization_basis",
        "rank_method",
    ]

    required_columns = {
        "metric_id",
        "metric_name",
        "country_code",
        "country_name",
        "value",
        "normalized_value",
        "rank",
        "year",
    }

    assert required_columns.issubset(api_table.columns)

    columns = [
        column
        for column in presentation_columns
        if column in api_table.columns
    ]

    result = api_table.loc[:, columns].copy()

    result = result.sort_values(
        by=[
            "metric_id",
            "rank",
            "country_name",
        ],
        ascending=[
            True,
            True,
            True,
        ],
    ).reset_index(drop=True)

    numeric_columns = result.select_dtypes(
        include="number"
    ).columns

    result.loc[:, numeric_columns] = (
        result.loc[:, numeric_columns].round(3)
    )

    return result


def _expected_weighted_score_ui_table(
    api_table: pd.DataFrame,
) -> pd.DataFrame:
    presentation_columns = [
        "country_code",
        "country_name",
        "weighted_score",
        "score_rank",
        "profile_name",
        "missing_data_policy",
        "metric_count_used",
        "metric_count_expected",
        "missing_metric_count",
        "missing_metrics",
        "weight_sum_used",
        "year_strategy",
        "score_rank_method",
    ]

    required_columns = {
        "country_code",
        "country_name",
        "weighted_score",
        "score_rank",
    }

    assert required_columns.issubset(
        api_table.columns
    )

    columns = [
        column
        for column in presentation_columns
        if column in api_table.columns
    ]

    result = api_table.loc[:, columns].copy()

    result = result.sort_values(
        by="score_rank",
        ascending=True,
        kind="stable",
    ).reset_index(drop=True)

    numeric_columns = result.select_dtypes(
        include="number"
    ).columns

    result.loc[:, numeric_columns] = (
        result.loc[:, numeric_columns].round(3)
    )

    return result


def _select_compare_tab(
    page: Page,
    label: str,
) -> None:
    tab = page.get_by_role(
        "tab",
        name=label,
        exact=True,
    )

    expect(tab).to_be_visible(timeout=20_000)

    tab.click()

    expect(tab).to_have_attribute(
        "aria-selected",
        "true",
        timeout=20_000,
    )


def _download_table_csv(page: Page) -> bytes:
    download_button = page.get_by_role(
        "button",
        name="Download table CSV",
        exact=True,
    )

    expect(download_button).to_be_visible(
        timeout=20_000
    )

    with page.expect_download(
        timeout=20_000
    ) as download_info:
        download_button.click()

    download_path = download_info.value.path()

    assert isinstance(download_path, Path)

    return download_path.read_bytes()


def _find_single_metric_reference_case() -> tuple[
    list[str],
    str,
    dict[str, object],
]:
    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    candidate_country_codes = [
        str(country["code"])
        for country in countries[:12]
        if isinstance(country, dict) and country.get("code")
    ]

    assert len(candidate_country_codes) >= 2

    for metric in metrics:
        if not isinstance(metric, dict):
            continue

        metric_id = str(metric.get("metric_id") or "").strip()

        if not metric_id:
            continue

        request_payload: dict[str, object] = {
            "country_codes": candidate_country_codes,
            "metric_id": metric_id,
            "year_strategy": "latest_per_metric",
        }

        status_code, envelope = _api_post_json(
            "/api/v1/compare/single-metric",
            request_payload,
        )

        if status_code != 200 or envelope.get("ok") is not True:
            continue

        table = _main_table_dataframe(envelope)

        if "country_code" not in table.columns:
            continue

        result_country_codes = list(
            dict.fromkeys(
                str(code)
                for code in table["country_code"].tolist()
                if str(code).strip()
            )
        )

        if len(result_country_codes) < 2:
            continue

        selected_country_codes = result_country_codes[:2]

        final_request: dict[str, object] = {
            "country_codes": selected_country_codes,
            "metric_id": metric_id,
            "year_strategy": "latest_per_metric",
        }

        final_status, final_envelope = _api_post_json(
            "/api/v1/compare/single-metric",
            final_request,
        )

        if (
            final_status == 200
            and final_envelope.get("ok") is True
            and len(_main_table_dataframe(final_envelope).index) >= 2
        ):
            return (
                selected_country_codes,
                metric_id,
                final_envelope,
            )

    raise AssertionError(
        "Could not discover a valid two-country " "single-metric E2E reference case."
    )


def _find_multi_metric_reference_case() -> tuple[
    list[str],
    list[str],
    dict[str, object],
]:
    (
        country_codes,
        first_metric_id,
        _single_envelope,
    ) = _find_single_metric_reference_case()

    metrics_payload = _api_get_json(
        "/api/v1/metadata/metrics"
    )

    metrics = metrics_payload.get("metrics")

    assert isinstance(metrics, list)

    for metric in metrics:
        if not isinstance(metric, dict):
            continue

        second_metric_id = str(
            metric.get("metric_id") or ""
        ).strip()

        if (
            not second_metric_id
            or second_metric_id == first_metric_id
        ):
            continue

        # First prove that the same two countries have a usable
        # result for the second metric.
        second_status, second_envelope = _api_post_json(
            "/api/v1/compare/single-metric",
            {
                "country_codes": country_codes,
                "metric_id": second_metric_id,
                "year_strategy": "latest_per_metric",
            },
        )

        if (
            second_status != 200
            or second_envelope.get("ok") is not True
        ):
            continue

        second_table = _main_table_dataframe(
            second_envelope
        )

        if len(second_table.index) < 2:
            continue

        metric_ids = [
            first_metric_id,
            second_metric_id,
        ]

        status_code, envelope = _api_post_json(
            "/api/v1/compare/multi-metric",
            {
                "country_codes": country_codes,
                "metric_ids": metric_ids,
                "year_strategy": "latest_per_metric",
            },
        )

        if (
            status_code != 200
            or envelope.get("ok") is not True
        ):
            continue

        table = _main_table_dataframe(envelope)

        if not {
            "country_code",
            "metric_id",
        }.issubset(table.columns):
            continue

        returned_metrics = {
            str(value)
            for value in table["metric_id"].tolist()
        }

        returned_countries = {
            str(value)
            for value in table["country_code"].tolist()
        }

        if not set(metric_ids).issubset(
            returned_metrics
        ):
            continue

        if not set(country_codes).issubset(
            returned_countries
        ):
            continue

        return (
            country_codes,
            metric_ids,
            envelope,
        )

    raise AssertionError(
        "Could not discover a two-country, "
        "two-metric E2E reference case."
    )


def _find_weighted_score_reference_case() -> tuple[
    list[str],
    str,
    dict[str, object],
]:
    countries_payload = _api_get_json(
        "/api/v1/metadata/countries"
    )
    profiles_payload = _api_get_json(
        "/api/v1/metadata/profiles"
    )

    countries = countries_payload.get("countries")
    profiles = profiles_payload.get("profiles")

    assert isinstance(countries, list)
    assert isinstance(profiles, list)

    candidate_country_codes = [
        str(country["code"])
        for country in countries[:40]
        if (
            isinstance(country, dict)
            and country.get("code")
        )
    ]

    assert len(candidate_country_codes) >= 2

    for profile in profiles:
        if not isinstance(profile, dict):
            continue

        profile_name = str(
            profile.get("profile_name")
            or profile.get("name")
            or ""
        ).strip()

        if not profile_name:
            continue

        status_code, envelope = _api_post_json(
            "/api/v1/score/profile",
            {
                "country_codes": (
                    candidate_country_codes
                ),
                "profile_name": profile_name,
                "year_strategy": (
                    "latest_per_metric"
                ),
            },
        )

        if (
            status_code != 200
            or envelope.get("ok") is not True
        ):
            continue

        table = _main_table_dataframe(
            envelope
        )

        if (
            "country_code" not in table.columns
            or len(table.index) < 2
        ):
            continue

        returned_country_codes = list(
            dict.fromkeys(
                str(code)
                for code in table[
                    "country_code"
                ].tolist()
                if str(code).strip()
            )
        )

        if len(returned_country_codes) < 2:
            continue

        selected_country_codes = (
            returned_country_codes[:2]
        )

        final_status, final_envelope = (
            _api_post_json(
                "/api/v1/score/profile",
                {
                    "country_codes": (
                        selected_country_codes
                    ),
                    "profile_name": profile_name,
                    "year_strategy": (
                        "latest_per_metric"
                    ),
                },
            )
        )

        if (
            final_status != 200
            or final_envelope.get("ok")
            is not True
        ):
            continue

        final_table = _main_table_dataframe(
            final_envelope
        )

        if len(final_table.index) < 2:
            continue

        return (
            selected_country_codes,
            profile_name,
            final_envelope,
        )

    raise AssertionError(
        "Could not discover a valid "
        "two-country weighted-score E2E case."
    )


def _find_backtest_reference_case(
) -> tuple[
    str,
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    holdout_years = 3

    countries_payload = _api_get_json(
        "/api/v1/metadata/countries"
    )
    metrics_payload = _api_get_json(
        "/api/v1/metadata/metrics"
    )

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(
            item.get("code")
            or item.get("country_code")
            or ""
        )
        .strip()
        .upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(
            item.get("metric_id")
            or item.get("id")
            or ""
        ).strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [
        value for value in country_codes if value
    ]
    metric_ids = [
        value for value in metric_ids if value
    ]

    for metric_id in metric_ids:
        for country_code in country_codes:
            status_code, envelope = _api_post_json(
                "/api/v1/prediction/backtest",
                {
                    "country_codes": [country_code],
                    "metric_id": metric_id,
                    "method": method,
                    "fallback_method": "last_observed",
                    "holdout_years": holdout_years,
                    "scenario_id": "baseline",
                },
            )

            if status_code != 200:
                continue

            if envelope.get("ok") is not True:
                continue

            try:
                actual_vs_predicted = (
                    _named_table_dataframe(
                        envelope,
                        "actual_vs_predicted",
                    )
                )
            except AssertionError:
                continue

            summary = envelope.get("summary")
            if not isinstance(summary, dict):
                continue

            metrics_summary = summary.get("metrics")
            if not isinstance(metrics_summary, dict):
                continue

            diagnostics = summary.get("diagnostics")
            if not isinstance(diagnostics, dict):
                continue

            items = diagnostics.get("items")
            if not isinstance(items, list):
                continue

            if len(actual_vs_predicted.index) != holdout_years:
                continue

            if len(items) != 1:
                continue

            diagnostic = items[0]
            if not isinstance(diagnostic, dict):
                continue

            if diagnostic.get("country_code") != country_code:
                continue

            if diagnostic.get("metric_id") != metric_id:
                continue

            if (
                diagnostic.get("method_requested")
                != method
            ):
                continue

            if diagnostic.get("method_used") != method:
                continue

            if diagnostic.get("fallback_used") is not False:
                continue

            if metrics_summary.get("method_used") != method:
                continue

            # UI-11 explicitly validates all three metrics.
            if metrics_summary.get("mae") is None:
                continue
            if metrics_summary.get("rmse") is None:
                continue
            if metrics_summary.get("mape") is None:
                continue

            return (
                country_code,
                metric_id,
                method,
                holdout_years,
                envelope,
            )

    pytest.fail(
        "Could not find a release-dataset series "
        "suitable for the deterministic UI-11 "
        "backtest reference case."
    )


def _ui_metric_value(value: object) -> str:
    if value is None or value == "":
        return "—"

    if isinstance(value, float):
        return f"{value:.4g}"

    return str(value)


def _assert_streamlit_metric(
    page: Page,
    *,
    label: str,
    value: object,
) -> None:
    metric = page.locator(
        '[data-testid="stMetric"]'
    ).filter(
        has_text=label
    ).first

    expect(metric).to_be_visible(timeout=20_000)
    expect(metric).to_contain_text(label)
    expect(metric).to_contain_text(
        _ui_metric_value(value)
    )


def _compare_url(
    *,
    countries: list[str],
    mode: str,
    metric: str | None = None,
    metrics: list[str] | None = None,
    profile: str | None = None,
) -> str:
    params: dict[str, str] = {
        "page": "Compare",
        "mode": mode,
        "countries": ",".join(countries),
        "year_strategy": "latest_per_metric",
    }

    if metric:
        params["metric"] = metric

    if metrics:
        params["metrics"] = ",".join(metrics)

    if profile:
        params["profile"] = profile

    return f"{UI_BASE_URL}/?{urlencode(params)}"


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        yield browser

        browser.close()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    page = context.new_page()

    yield page

    context.close()


def _api_headers() -> dict[str, str]:
    if not API_KEY:
        return {}

    return {
        "X-API-Key": API_KEY,
    }


def _api_get_json(path: str) -> dict[str, object]:
    response = httpx.get(
        f"{API_BASE_URL}{path}",
        headers=_api_headers(),
        timeout=20.0,
    )

    response.raise_for_status()

    payload = response.json()

    assert isinstance(payload, dict)

    return payload


def _api_post_json(
    path: str,
    payload: dict[str, object],
) -> tuple[int, dict[str, object]]:
    response = httpx.post(
        f"{API_BASE_URL}{path}",
        headers=_api_headers(),
        json=payload,
        timeout=30.0,
    )

    body = response.json()

    assert isinstance(body, dict)

    return response.status_code, body


def _dataset_metadata() -> dict[str, object]:
    response = httpx.get(
        f"{API_BASE_URL}/api/v1/metadata/dataset",
        headers=_api_headers(),
        timeout=20.0,
    )

    response.raise_for_status()

    return response.json()


def _open_overview(page: Page) -> None:
    page.goto(
        UI_BASE_URL,
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_text(
            "Country Comparison — Overview",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)


def _metric_value(page: Page, label: str) -> str:
    metric = page.locator('[data-testid="stMetric"]').filter(has_text=label).first

    expect(metric).to_be_visible()

    return metric.locator('[data-testid="stMetricValue"]').inner_text().strip()


@pytest.mark.e2e
def test_ui_01_overview_matches_backend_dataset_metadata(
    page: Page,
) -> None:
    metadata = _dataset_metadata()

    _open_overview(page)

    row_count = metadata["row_count"]
    country_count = metadata["country_count"]
    metric_count = metadata["metric_count"]
    year_min = metadata["year_min"]
    year_max = metadata["year_max"]

    assert int(_metric_value(page, "Rows").replace(",", "")) == row_count

    assert (
        int(
            _metric_value(
                page,
                "Countries",
            ).replace(",", "")
        )
        == country_count
    )

    assert (
        int(
            _metric_value(
                page,
                "Metrics",
            ).replace(",", "")
        )
        == metric_count
    )

    assert _metric_value(page, "Year range") == (f"{year_min}–{year_max}")


@pytest.mark.e2e
def test_ui_02_http_runtime_exposes_only_production_pages(
    page: Page,
) -> None:
    _open_overview(page)

    expect(
        page.get_by_role(
            "radio",
            name="Overview",
            exact=True,
        )
    ).to_be_visible()

    expect(
        page.get_by_role(
            "radio",
            name="Compare",
            exact=True,
        )
    ).to_be_visible()

    expect(
        page.get_by_role(
            "radio",
            name="Prediction",
            exact=True,
        )
    ).to_be_visible()

    assert (
        page.get_by_role(
            "radio",
            name="Config Editor",
            exact=True,
        ).count()
        == 0
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("page_label", "expected_heading"),
    [
        ("Compare", "Compare"),
        ("Prediction", "Prediction"),
    ],
)
def test_ui_02_production_page_is_navigable(
    page: Page,
    page_label: str,
    expected_heading: str,
) -> None:
    _open_overview(page)

    _select_sidebar_page(
        page,
        page_label,
    )

    expect(
        page.get_by_role(
            "heading",
            name=expected_heading,
            exact=True,
        )
    ).to_be_visible(timeout=20_000)


@pytest.mark.e2e
def test_ui_03_single_metric_csv_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        api_envelope,
    ) = _find_single_metric_reference_case()

    expected_table = _main_table_dataframe(api_envelope)

    expected_csv = _csv_bytes(expected_table)

    page.goto(
        _compare_url(
            countries=country_codes,
            mode="single_metric",
            metric=metric_id,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Compare",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    run_button = page.get_by_role(
        "button",
        name="Run single-metric comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_text(
            "Single-metric comparison completed successfully.",
            exact=True,
        )
    ).to_be_visible(timeout=20_000)

    download_button = page.get_by_role(
        "button",
        name="Download table CSV",
        exact=True,
    )

    expect(download_button).to_be_visible(timeout=20_000)

    with page.expect_download(timeout=20_000) as download_info:
        download_button.click()

    download = download_info.value
    download_path = download.path()

    assert isinstance(download_path, Path)

    actual_csv = _download_table_csv(page)

    assert actual_csv == expected_csv


@pytest.mark.e2e
def test_ui_04_multi_metric_csv_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_ids,
        api_envelope,
    ) = _find_multi_metric_reference_case()

    api_table = _main_table_dataframe(
        api_envelope
    )

    assert set(
        api_table["metric_id"].astype(str)
    ) == set(metric_ids)

    expected_table = (
        _expected_multi_metric_ui_table(
            api_table
        )
    )

    expected_csv = _csv_bytes(
        expected_table
    )

    page.goto(
        _compare_url(
            countries=country_codes,
            mode="multi_metric",
            metrics=metric_ids,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Compare",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _select_compare_tab(
        page,
        "Multi Metric",
    )

    run_button = page.get_by_role(
        "button",
        name="Run multi-metric comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(
        timeout=20_000
    )

    run_button.click()

    # A Streamlit rerun can reset tab presentation state,
    # so explicitly restore the tab before inspecting results.
    _select_compare_tab(
        page,
        "Multi Metric",
    )

    expect(
        page.get_by_text(
            "Multi-metric comparison completed successfully.",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    actual_csv = _download_table_csv(page)

    assert actual_csv == expected_csv


@pytest.mark.e2e
def test_ui_05_weighted_score_csv_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        profile_name,
        api_envelope,
    ) = _find_weighted_score_reference_case()

    api_table = _main_table_dataframe(
        api_envelope
    )

    required_columns = {
        "country_code",
        "weighted_score",
        "score_rank",
    }

    assert required_columns.issubset(
        api_table.columns
    )

    for column in (
        "metric_count_used",
        "metric_count_expected",
        "weight_sum_used",
    ):
        assert column in api_table.columns

    expected_table = (
        _expected_weighted_score_ui_table(
            api_table
        )
    )

    expected_csv = _csv_bytes(
        expected_table
    )
    page.goto(
        _compare_url(
            countries=country_codes,
            mode="weighted_score",
            profile=profile_name,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Compare",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _select_compare_tab(
        page,
        "Weighted Score",
    )

    run_button = page.get_by_role(
        "button",
        name="Run weighted-score comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(
        timeout=20_000
    )

    run_button.click()

    _select_compare_tab(
        page,
        "Weighted Score",
    )

    expect(
        page.get_by_text(
            "Weighted scoring completed successfully.",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    actual_csv = _download_table_csv(page)

    assert actual_csv == expected_csv


@pytest.mark.e2e
def test_ui_06_single_country_forecast_matches_backend_result(
    page: Page,
) -> None:
    (
        country_code,
        metric_id,
        method,
        horizon_years,
        api_envelope,
    ) = _find_single_forecast_reference_case()

    expected_table = _expected_forecast_ui_table(
        api_envelope
    )
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get(
        "diagnostics"
    )
    assert isinstance(expected_diagnostics, dict)

    expected_items = expected_diagnostics.get("items")
    assert isinstance(expected_items, list)
    assert len(expected_items) == 1

    expected_diagnostic = expected_items[0]
    assert isinstance(expected_diagnostic, dict)

    assert (
        expected_diagnostic["method_requested"]
        == method
    )
    assert expected_diagnostic["method_used"] == method
    assert expected_diagnostic["fallback_used"] is False

    page.goto(
        _prediction_url(
            mode="single_forecast",
            country=country_code,
            metric=metric_id,
            method=method,
            horizon_years=horizon_years,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Prediction",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _select_prediction_tab(
        page,
        "Single Forecast",
    )

    run_button = page.get_by_role(
        "button",
        name="Run single forecast",
        exact=True,
    )

    expect(run_button).to_be_visible(
        timeout=20_000
    )

    run_button.click()

    # Streamlit reruns can reset the visible tab.
    _select_prediction_tab(
        page,
        "Single Forecast",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Forecast table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_role(
            "heading",
            name="Prediction quality",
            exact=True,
        )
    ).to_be_visible(timeout=20_000)

    actual_csv = _download_table_csv(page)

    _assert_prediction_run_metadata(expected_csv)
    _assert_prediction_run_metadata(actual_csv)

    expected_comparable_csv = _csv_without_columns(
        expected_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    actual_comparable_csv = _csv_without_columns(
        actual_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    assert actual_comparable_csv == expected_comparable_csv

    actual_diagnostics_payload = (
        _download_diagnostics_json(page)
    )

    actual_summary = actual_diagnostics_payload.get(
        "summary"
    )
    assert isinstance(actual_summary, dict)

    actual_diagnostics = actual_summary.get(
        "diagnostics"
    )

    assert actual_diagnostics == expected_diagnostics


@pytest.mark.e2e
def test_ui_07_multi_country_forecast_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        method,
        horizon_years,
        api_envelope,
    ) = _find_multi_country_forecast_reference_case()

    assert len(country_codes) == 2

    expected_table = _expected_forecast_ui_table(
        api_envelope
    )
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get(
        "diagnostics"
    )
    assert isinstance(expected_diagnostics, dict)

    expected_by_country = (
        _prediction_diagnostics_by_country(
            expected_diagnostics
        )
    )

    assert set(expected_by_country) == set(
        country_codes
    )

    for country_code in country_codes:
        diagnostic = expected_by_country[country_code]

        assert diagnostic["country_code"] == country_code
        assert diagnostic["metric_id"] == metric_id
        assert diagnostic["method_requested"] == method
        assert diagnostic["method_used"] == method
        assert diagnostic["fallback_used"] is False

    page.goto(
        _prediction_url(
            mode="multi_country_forecast",
            countries=country_codes,
            metric=metric_id,
            method=method,
            horizon_years=horizon_years,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Prediction",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _select_prediction_tab(
        page,
        "Multi-Country Forecast",
    )

    run_button = page.get_by_role(
        "button",
        name="Run multi-country forecast",
        exact=True,
    )

    expect(run_button).to_be_visible(
        timeout=20_000
    )

    run_button.click()

    # Streamlit reruns can reset the visible tab.
    _select_prediction_tab(
        page,
        "Multi-Country Forecast",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Forecast table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_role(
            "heading",
            name="Prediction quality",
            exact=True,
        )
    ).to_be_visible(timeout=20_000)

    actual_csv = _download_table_csv(page)

    _assert_prediction_run_metadata(
        expected_csv
    )
    _assert_prediction_run_metadata(
        actual_csv
    )

    expected_comparable_csv = _csv_without_columns(
        expected_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )
    actual_comparable_csv = _csv_without_columns(
        actual_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    assert (
        actual_comparable_csv
        == expected_comparable_csv
    )

    actual_diagnostics_payload = (
        _download_diagnostics_json(page)
    )

    actual_summary = actual_diagnostics_payload.get(
        "summary"
    )
    assert isinstance(actual_summary, dict)

    actual_diagnostics = actual_summary.get(
        "diagnostics"
    )
    assert isinstance(actual_diagnostics, dict)

    actual_by_country = (
        _prediction_diagnostics_by_country(
            actual_diagnostics
        )
    )

    assert actual_by_country == expected_by_country


@pytest.mark.e2e
def test_ui_11_backtest_matches_backend_result(
    page: Page,
) -> None:
    (
        country_code,
        metric_id,
        method,
        holdout_years,
        api_envelope,
    ) = _find_backtest_reference_case()

    expected_table = _named_table_dataframe(
        api_envelope,
        "actual_vs_predicted",
    )
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_metrics = expected_summary.get("metrics")
    assert isinstance(expected_metrics, dict)

    expected_diagnostics = expected_summary.get(
        "diagnostics"
    )
    assert isinstance(expected_diagnostics, dict)

    assert expected_metrics["method_used"] == method
    assert expected_metrics["fallback_used"] is False
    assert expected_metrics["mae"] is not None
    assert expected_metrics["rmse"] is not None
    assert expected_metrics["mape"] is not None

    assert (
        expected_metrics["n_test_observations"]
        == holdout_years
    )

    page.goto(
        _prediction_url(
            mode="backtest",
            country=country_code,
            metric=metric_id,
            method=method,
            holdout_years=holdout_years,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    expect(
        page.get_by_role(
            "heading",
            name="Prediction",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _select_prediction_tab(
        page,
        "Backtest",
    )

    run_button = page.get_by_role(
        "button",
        name="Run backtest",
        exact=True,
    )

    expect(run_button).to_be_visible(
        timeout=20_000
    )
    run_button.click()

    # Streamlit reruns can restore the first tab.
    _select_prediction_tab(
        page,
        "Backtest",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Actual vs predicted",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _assert_streamlit_metric(
        page,
        label="Method used",
        value=expected_metrics["method_used"],
    )
    _assert_streamlit_metric(
        page,
        label="MAE",
        value=expected_metrics["mae"],
    )
    _assert_streamlit_metric(
        page,
        label="RMSE",
        value=expected_metrics["rmse"],
    )
    _assert_streamlit_metric(
        page,
        label="MAPE",
        value=expected_metrics["mape"],
    )

    actual_csv = _download_table_csv(page)

    # A separate browser-triggered backtest receives a
    # fresh UUID/timestamp, just like UI-06/UI-07.
    _assert_prediction_run_metadata(expected_csv)
    _assert_prediction_run_metadata(actual_csv)

    expected_comparable_csv = _csv_without_columns(
        expected_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )
    actual_comparable_csv = _csv_without_columns(
        actual_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    assert (
        actual_comparable_csv
        == expected_comparable_csv
    )

    actual_diagnostics_payload = (
        _download_diagnostics_json(page)
    )

    actual_summary = actual_diagnostics_payload.get(
        "summary"
    )
    assert isinstance(actual_summary, dict)

    actual_metrics = actual_summary.get("metrics")
    assert isinstance(actual_metrics, dict)

    actual_diagnostics = actual_summary.get(
        "diagnostics"
    )
    assert isinstance(actual_diagnostics, dict)

    assert actual_metrics == expected_metrics
    assert actual_diagnostics == expected_diagnostics    