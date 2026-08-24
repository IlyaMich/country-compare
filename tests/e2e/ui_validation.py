from __future__ import annotations

import json
import os
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from country_compare.prediction import (
    build_line_chart_dataframe,
)
from country_compare.ui.components.prediction_result_panels import (
    build_backtest_line_chart_dataframe,
    build_predicted_comparison_chart_dataframe,
    build_streamlit_line_chart_table,
)
from country_compare.ui.components.result_panels import (
    build_comparison_chart_dataframe,
    build_multi_metric_comparison_chart_dataframe,
)

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

_UI_14_BASE_PREDICTION_LIMITATIONS = (
    ("Forecasts are baseline statistical " "projections, not guarantees."),
    (
        "The module extrapolates from historical "
        "metric values and does not model causal "
        "drivers."
    ),
    (
        "Unexpected shocks, policy changes, "
        "methodology changes, or source revisions "
        "are not predicted."
    ),
    ("Confidence intervals are not available " "in the current baseline output."),
    ("Sparse, stale, or irregular histories " "should be treated with extra caution."),
)


def _open_streamlit_expander(
    page: Page,
    label: str,
):
    expander = page.locator('[data-testid="stExpander"]').filter(has_text=label).first

    expect(expander).to_be_visible(timeout=20_000)

    details = expander.locator("details")

    if details.get_attribute("open") is None:
        expander.locator("summary").click()

    return expander


def _csv_without_columns(
    payload: bytes,
    columns: tuple[str, ...],
) -> bytes:
    dataframe = pd.read_csv(
        BytesIO(payload),
        dtype=str,
        keep_default_na=False,
    )

    removable = [column for column in columns if column in dataframe.columns]

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


def _find_single_forecast_reference_case() -> tuple[
    str,
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    horizon_years = 3

    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(item.get("code") or item.get("country_code") or "").strip().upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "").strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [value for value in country_codes if value]
    metric_ids = [value for value in metric_ids if value]

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
                diagnostics = _prediction_diagnostic_items(envelope)
            except AssertionError:
                continue

            if len(forecast.index) != horizon_years:
                continue

            if len(diagnostics) != 1:
                continue

            diagnostic = diagnostics[0]

            if diagnostic.get("country_code") != country_code:
                continue

            if diagnostic.get("metric_id") != metric_id:
                continue

            if diagnostic.get("method_requested") != method:
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


def _find_multi_country_forecast_reference_case() -> tuple[
    list[str],
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    horizon_years = 3

    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(item.get("code") or item.get("country_code") or "").strip().upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "").strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [value for value in country_codes if value]
    metric_ids = [value for value in metric_ids if value]

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
                diagnostics = _prediction_diagnostic_items(single_envelope)
            except AssertionError:
                continue

            if len(forecast.index) != horizon_years:
                continue

            if len(diagnostics) != 1:
                continue

            diagnostic = diagnostics[0]

            if diagnostic.get("country_code") != country_code:
                continue

            if diagnostic.get("metric_id") != metric_id:
                continue

            if diagnostic.get("method_requested") != method:
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
                batch_diagnostics = _prediction_diagnostic_items(batch_envelope)
            except AssertionError:
                continue

            if len(batch_forecast.index) != len(selected_countries) * horizon_years:
                continue

            if len(batch_diagnostics) != len(selected_countries):
                continue

            forecast_country_codes = set(
                batch_forecast["country_code"].astype(str).tolist()
            )

            if forecast_country_codes != set(selected_countries):
                continue

            diagnostics_by_country = {
                str(item.get("country_code")): item for item in batch_diagnostics
            }

            if set(diagnostics_by_country) != set(selected_countries):
                continue

            valid = True

            for code in selected_countries:
                diagnostic = diagnostics_by_country[code]

                if diagnostic.get("metric_id") != metric_id:
                    valid = False
                    break

                if diagnostic.get("method_requested") != method:
                    valid = False
                    break

                if diagnostic.get("method_used") != method:
                    valid = False
                    break

                if diagnostic.get("fallback_used") is not False:
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


def _find_predicted_single_metric_reference_case() -> tuple[
    list[str],
    str,
    str,
    int,
    int,
    dict[str, object],
]:
    (
        country_codes,
        metric_id,
        method,
        horizon_years,
        _,
    ) = _find_multi_country_forecast_reference_case()

    forecast_horizon = 1

    status_code, envelope = _api_post_json(
        "/api/v1/prediction/compare/single-metric",
        {
            "country_codes": country_codes,
            "metric_id": metric_id,
            "horizon_years": horizon_years,
            "forecast_horizon": forecast_horizon,
            "method": method,
            "fallback_method": "last_observed",
            "comparison_options": {},
        },
    )

    assert status_code == 200
    assert envelope.get("ok") is True

    comparison = _named_table_dataframe(
        envelope,
        "predicted_comparison",
    )

    summary = envelope.get("summary")
    assert isinstance(summary, dict)

    assert summary.get("selected_forecast_horizon") == forecast_horizon

    selected_year = summary.get("selected_forecast_year")

    assert selected_year is None or isinstance(selected_year, int)

    metadata = summary.get("metadata")
    assert isinstance(metadata, dict)

    selected_prediction_years = metadata.get("selected_prediction_years")
    assert isinstance(selected_prediction_years, list)
    assert selected_prediction_years

    selected_prediction_years = [int(year) for year in selected_prediction_years]

    comparison_years = sorted(
        pd.to_numeric(
            comparison["year"],
            errors="raise",
        )
        .astype(int)
        .unique()
        .tolist()
    )

    assert comparison_years == sorted(selected_prediction_years)

    if selected_year is not None:
        assert selected_prediction_years == [selected_year]
    else:
        # Horizon-based selection may map to different
        # calendar years when countries have different
        # forecast origin years.
        assert len(selected_prediction_years) > 1

    assert len(comparison.index) == len(country_codes)

    assert "country_code" in comparison.columns
    assert "year" in comparison.columns
    assert "value" in comparison.columns
    assert "normalized_value" in comparison.columns
    assert "rank" in comparison.columns

    assert set(comparison["country_code"].astype(str).tolist()) == set(country_codes)

    assert comparison["value"].notna().all()
    assert comparison["normalized_value"].notna().all()
    assert comparison["rank"].notna().all()

    return (
        country_codes,
        metric_id,
        method,
        horizon_years,
        forecast_horizon,
        envelope,
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
            dataframe["row_type"].astype("string").eq("predicted")
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
    metric: str | None = None,
    metrics: list[str] | None = None,
    profile: str | None = None,
    horizon_years: int | None = None,
    holdout_years: int | None = None,
    country: str | None = None,
    countries: list[str] | None = None,
    forecast_horizon: int | None = None,
    forecast_year: int | None = None,
) -> str:
    params: dict[str, str] = {
        "page": "Prediction",
        "prediction_mode": mode,
        "prediction_method": method,
    }

    if metric is not None:
        params["prediction_metric"] = metric

    if metrics:
        params["prediction_metrics"] = ",".join(metrics)

    if profile is not None:
        params["prediction_profile"] = profile

    if country is not None:
        params["prediction_country"] = country

    if countries:
        params["prediction_countries"] = ",".join(countries)

    if horizon_years is not None:
        params["prediction_horizon_years"] = str(horizon_years)

    if holdout_years is not None:
        params["prediction_holdout_years"] = str(holdout_years)

    if forecast_horizon is not None:
        params["prediction_forecast_horizon"] = str(forecast_horizon)

    if forecast_year is not None:
        params["prediction_forecast_year"] = str(forecast_year)

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

    expect(download_button).to_be_visible(timeout=20_000)

    with page.expect_download(timeout=20_000) as download_info:
        download_button.click()

    download_path = download_info.value.path()
    assert isinstance(download_path, Path)

    payload = json.loads(download_path.read_text(encoding="utf-8"))

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

    columns = [column for column in presentation_columns if column in api_table.columns]

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

    numeric_columns = result.select_dtypes(include="number").columns

    result.loc[:, numeric_columns] = result.loc[:, numeric_columns].round(3)

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

    assert required_columns.issubset(api_table.columns)

    columns = [column for column in presentation_columns if column in api_table.columns]

    result = api_table.loc[:, columns].copy()

    result = result.sort_values(
        by="score_rank",
        ascending=True,
        kind="stable",
    ).reset_index(drop=True)

    numeric_columns = result.select_dtypes(include="number").columns

    result.loc[:, numeric_columns] = result.loc[:, numeric_columns].round(3)

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

    expect(download_button).to_be_visible(timeout=20_000)

    with page.expect_download(timeout=20_000) as download_info:
        download_button.click()

    download_path = download_info.value.path()

    assert isinstance(download_path, Path)

    return download_path.read_bytes()


def _download_summary_markdown(
    page: Page,
) -> str:
    download_button = page.get_by_role(
        "button",
        name="Download summary Markdown",
        exact=True,
    )

    expect(download_button).to_be_visible(timeout=20_000)

    with page.expect_download(timeout=20_000) as download_info:
        download_button.click()

    download_path = download_info.value.path()

    assert isinstance(download_path, Path)

    return download_path.read_text(encoding="utf-8")


def _assert_exports_contain_no_secrets(
    *payloads: bytes | str,
) -> None:
    combined = "\n".join(
        (
            payload.decode(
                "utf-8",
                errors="replace",
            )
            if isinstance(payload, bytes)
            else payload
        )
        for payload in payloads
    )

    secret_env_names = (
        "COUNTRY_COMPARE_E2E_API_KEY",
        "COUNTRY_COMPARE_API_KEY",
        "COUNTRY_COMPARE_LLM_SERVICE_TOKEN",
        "MISTRAL_API_KEY",
    )

    for env_name in secret_env_names:
        secret = os.getenv(env_name)

        if secret and secret in combined:
            pytest.fail(
                "Export payload leaked a " f"configured secret from {env_name}."
            )


def _assert_export_csv_matches_api_columns(
    *,
    csv_payload: bytes,
    api_table: pd.DataFrame,
    sort_columns: tuple[str, ...],
) -> None:
    actual = pd.read_csv(
        BytesIO(csv_payload),
    )

    assert not actual.empty

    missing_api_columns = [
        column for column in actual.columns if column not in api_table.columns
    ]

    assert not missing_api_columns, (
        "Export contains columns that cannot "
        "be matched to the API table: "
        f"{missing_api_columns}"
    )

    expected = api_table.loc[
        :,
        list(actual.columns),
    ].copy()

    usable_sort_columns = [
        column
        for column in sort_columns
        if (column in actual.columns and column in expected.columns)
    ]

    if usable_sort_columns:
        actual = actual.sort_values(
            usable_sort_columns,
            kind="stable",
        )
        expected = expected.sort_values(
            usable_sort_columns,
            kind="stable",
        )

    actual = actual.reset_index(drop=True)
    expected = expected.reset_index(drop=True)

    # CSV parsing converts empty fields to NaN,
    # while the API may represent the same
    # missing value as None or pd.NA.
    actual = actual.astype(object).where(pd.notna(actual), pd.NA)

    expected = expected.astype(object).where(pd.notna(expected), pd.NA)

    pd.testing.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def _prediction_method_available(
    method_id: str,
) -> bool:
    payload = _api_get_json("/api/v1/metadata/prediction-methods")

    methods = payload.get("methods")
    assert isinstance(methods, list)

    return any(
        isinstance(method, dict) and method.get("method_id") == method_id
        for method in methods
    )


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

    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    metrics = metrics_payload.get("metrics")

    assert isinstance(metrics, list)

    for metric in metrics:
        if not isinstance(metric, dict):
            continue

        second_metric_id = str(metric.get("metric_id") or "").strip()

        if not second_metric_id or second_metric_id == first_metric_id:
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

        if second_status != 200 or second_envelope.get("ok") is not True:
            continue

        second_table = _main_table_dataframe(second_envelope)

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

        if status_code != 200 or envelope.get("ok") is not True:
            continue

        table = _main_table_dataframe(envelope)

        if not {
            "country_code",
            "metric_id",
        }.issubset(table.columns):
            continue

        returned_metrics = {str(value) for value in table["metric_id"].tolist()}

        returned_countries = {str(value) for value in table["country_code"].tolist()}

        if not set(metric_ids).issubset(returned_metrics):
            continue

        if not set(country_codes).issubset(returned_countries):
            continue

        return (
            country_codes,
            metric_ids,
            envelope,
        )

    raise AssertionError(
        "Could not discover a two-country, " "two-metric E2E reference case."
    )


def _find_weighted_score_reference_case() -> tuple[
    list[str],
    str,
    dict[str, object],
]:
    countries_payload = _api_get_json("/api/v1/metadata/countries")
    profiles_payload = _api_get_json("/api/v1/metadata/profiles")

    countries = countries_payload.get("countries")
    profiles = profiles_payload.get("profiles")

    assert isinstance(countries, list)
    assert isinstance(profiles, list)

    candidate_country_codes = [
        str(country["code"])
        for country in countries[:40]
        if (isinstance(country, dict) and country.get("code"))
    ]

    assert len(candidate_country_codes) >= 2

    for profile in profiles:
        if not isinstance(profile, dict):
            continue

        profile_name = str(
            profile.get("profile_name") or profile.get("name") or ""
        ).strip()

        if not profile_name:
            continue

        status_code, envelope = _api_post_json(
            "/api/v1/score/profile",
            {
                "country_codes": (candidate_country_codes),
                "profile_name": profile_name,
                "year_strategy": ("latest_per_metric"),
            },
        )

        if status_code != 200 or envelope.get("ok") is not True:
            continue

        table = _main_table_dataframe(envelope)

        if "country_code" not in table.columns or len(table.index) < 2:
            continue

        returned_country_codes = list(
            dict.fromkeys(
                str(code)
                for code in table["country_code"].tolist()
                if str(code).strip()
            )
        )

        if len(returned_country_codes) < 2:
            continue

        selected_country_codes = returned_country_codes[:2]

        final_status, final_envelope = _api_post_json(
            "/api/v1/score/profile",
            {
                "country_codes": (selected_country_codes),
                "profile_name": profile_name,
                "year_strategy": ("latest_per_metric"),
            },
        )

        if final_status != 200 or final_envelope.get("ok") is not True:
            continue

        final_table = _main_table_dataframe(final_envelope)

        if len(final_table.index) < 2:
            continue

        return (
            selected_country_codes,
            profile_name,
            final_envelope,
        )

    raise AssertionError(
        "Could not discover a valid " "two-country weighted-score E2E case."
    )


def _find_backtest_reference_case() -> tuple[
    str,
    str,
    str,
    int,
    dict[str, object],
]:
    method = "last_observed"
    holdout_years = 3

    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(item.get("code") or item.get("country_code") or "").strip().upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "").strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [value for value in country_codes if value]
    metric_ids = [value for value in metric_ids if value]

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
                actual_vs_predicted = _named_table_dataframe(
                    envelope,
                    "actual_vs_predicted",
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

            if diagnostic.get("method_requested") != method:
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


def _find_predicted_multi_metric_reference_case() -> tuple[
    list[str],
    list[str],
    str,
    int,
    int,
    dict[str, object],
]:
    (
        country_codes,
        first_metric_id,
        method,
        horizon_years,
        _,
    ) = _find_multi_country_forecast_reference_case()

    forecast_horizon = 1

    metrics_payload = _api_get_json("/api/v1/metadata/metrics")
    metrics = metrics_payload.get("metrics")
    assert isinstance(metrics, list)

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "").strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    metric_ids = [
        metric_id
        for metric_id in metric_ids
        if metric_id and metric_id != first_metric_id
    ]

    for second_metric_id in metric_ids:
        selected_metric_ids = [
            first_metric_id,
            second_metric_id,
        ]

        status_code, envelope = _api_post_json(
            "/api/v1/prediction/compare/multi-metric",
            {
                "country_codes": country_codes,
                "metric_ids": selected_metric_ids,
                "horizon_years": horizon_years,
                "forecast_horizon": forecast_horizon,
                "method": method,
                "fallback_method": "last_observed",
                "comparison_options": {},
            },
        )

        if status_code != 200:
            continue

        if envelope.get("ok") is not True:
            continue

        try:
            comparison = _named_table_dataframe(
                envelope,
                "predicted_comparison",
            )
            diagnostics = _prediction_diagnostic_items(envelope)
        except AssertionError:
            continue

        summary = envelope.get("summary")
        if not isinstance(summary, dict):
            continue

        if summary.get("selected_forecast_horizon") != forecast_horizon:
            continue

        required_columns = {
            "country_code",
            "metric_id",
            "year",
            "value",
            "normalized_value",
            "rank",
        }

        if not required_columns.issubset(set(comparison.columns)):
            continue

        # Require a complete 2-country x 2-metric result.
        if len(comparison.index) != 4:
            continue

        if set(comparison["country_code"].astype(str).tolist()) != set(country_codes):
            continue

        if set(comparison["metric_id"].astype(str).tolist()) != set(
            selected_metric_ids
        ):
            continue

        pair_counts = comparison.groupby(
            ["country_code", "metric_id"],
            dropna=False,
        ).size()

        if not (pair_counts == 1).all():
            continue

        if len(pair_counts.index) != 4:
            continue

        if comparison["value"].isna().any():
            continue

        if comparison["normalized_value"].isna().any():
            continue

        if comparison["rank"].isna().any():
            continue

        # Require one clean diagnostic for every
        # country/metric forecast series.
        if len(diagnostics) != 4:
            continue

        diagnostics_by_series: dict[
            tuple[str, str],
            dict[str, object],
        ] = {}

        valid = True

        for diagnostic in diagnostics:
            country_code = diagnostic.get("country_code")
            metric_id = diagnostic.get("metric_id")

            if not isinstance(country_code, str):
                valid = False
                break

            if not isinstance(metric_id, str):
                valid = False
                break

            key = (country_code, metric_id)

            if key in diagnostics_by_series:
                valid = False
                break

            diagnostics_by_series[key] = diagnostic

            if diagnostic.get("method_requested") != method:
                valid = False
                break

            if diagnostic.get("method_used") != method:
                valid = False
                break

            if diagnostic.get("fallback_used") is not False:
                valid = False
                break

        expected_series = {
            (country_code, metric_id)
            for country_code in country_codes
            for metric_id in selected_metric_ids
        }

        if not valid:
            continue

        if set(diagnostics_by_series) != expected_series:
            continue

        metadata = summary.get("metadata")
        if not isinstance(metadata, dict):
            continue

        selected_prediction_years = metadata.get("selected_prediction_years")

        if not isinstance(
            selected_prediction_years,
            list,
        ):
            continue

        if not selected_prediction_years:
            continue

        return (
            country_codes,
            selected_metric_ids,
            method,
            horizon_years,
            forecast_horizon,
            envelope,
        )

    pytest.fail(
        "Could not find two release-dataset metrics "
        "and two countries suitable for the "
        "deterministic UI-09 predicted multi-metric "
        "comparison reference case."
    )


def _find_predicted_profile_reference_case() -> tuple[
    list[str],
    str,
    list[str],
    str,
    int,
    int,
    dict[str, object],
]:
    method = "last_observed"
    horizon_years = 3
    forecast_horizon = 1

    profiles_payload = _api_get_json("/api/v1/metadata/profiles")
    countries_payload = _api_get_json("/api/v1/metadata/countries")

    profiles = profiles_payload.get("profiles")
    countries = countries_payload.get("countries")

    assert isinstance(profiles, list)
    assert isinstance(countries, list)

    # Prefer smaller profiles first so reference discovery
    # remains reasonably fast.
    profiles = sorted(
        (profile for profile in profiles if isinstance(profile, dict)),
        key=lambda profile: int(profile.get("metric_count") or 10_000),
    )

    country_codes = [
        str(item.get("code") or item.get("country_code") or "").strip().upper()
        for item in countries
        if isinstance(item, dict)
    ]

    country_codes = [country_code for country_code in country_codes if country_code]

    for profile in profiles:
        profile_name = str(
            profile.get("profile_name") or profile.get("name") or ""
        ).strip()

        raw_metric_ids = profile.get("metric_ids")

        if not isinstance(
            raw_metric_ids,
            list,
        ):
            continue

        metric_ids = [
            str(metric_id).strip()
            for metric_id in raw_metric_ids
            if str(metric_id).strip()
        ]

        if not profile_name or not metric_ids:
            continue

        selected_countries = _find_countries_covering_profile(
            country_codes=country_codes,
            metric_ids=metric_ids,
            method=method,
            horizon_years=horizon_years,
        )

        if selected_countries is None:
            continue

        status_code, envelope = _api_post_json(
            "/api/v1/prediction/compare/profile",
            {
                "country_codes": (selected_countries),
                "profile_name": profile_name,
                "horizon_years": (horizon_years),
                "forecast_horizon": (forecast_horizon),
                "method": method,
                "fallback_method": ("last_observed"),
                "comparison_options": {},
            },
        )

        if status_code != 200:
            continue

        if envelope.get("ok") is not True:
            continue

        try:
            comparison = _named_table_dataframe(
                envelope,
                "predicted_comparison",
            )

            diagnostics = _prediction_diagnostic_items(envelope)
        except AssertionError:
            continue

        if comparison.empty:
            continue

        # Profile prediction produces a weighted-score
        # result, not the long per-metric table used by
        # predicted multi-metric comparison.
        required_columns = {
            "country_code",
            "weighted_score",
            "score_rank",
            "profile_name",
        }

        if not required_columns.issubset(set(comparison.columns)):
            continue

        if len(comparison.index) != len(selected_countries):
            continue

        result_countries = set(comparison["country_code"].astype(str).tolist())

        if result_countries != set(selected_countries):
            continue

        returned_profiles = set(comparison["profile_name"].astype(str).tolist())

        if returned_profiles != {profile_name}:
            continue

        if comparison["weighted_score"].isna().any():
            continue

        if comparison["score_rank"].isna().any():
            continue

        expected_series = {
            (
                country_code,
                metric_id,
            )
            for country_code in selected_countries
            for metric_id in metric_ids
        }

        diagnostics_by_series: dict[
            tuple[str, str],
            dict[str, object],
        ] = {}

        valid = True
        successful_diagnostic_count = 0

        for diagnostic in diagnostics:
            country_code = diagnostic.get("country_code")
            metric_id = diagnostic.get("metric_id")

            if not isinstance(
                country_code,
                str,
            ):
                valid = False
                break

            if not isinstance(
                metric_id,
                str,
            ):
                valid = False
                break

            key = (
                country_code,
                metric_id,
            )

            if key in diagnostics_by_series:
                valid = False
                break

            diagnostics_by_series[key] = diagnostic

            if diagnostic.get("method_requested") != method:
                valid = False
                break

            status = diagnostic.get("status")

            if status in {
                "ok",
                "warning",
            }:
                if diagnostic.get("method_used") != method:
                    valid = False
                    break

                if diagnostic.get("fallback_used") is not False:
                    valid = False
                    break

                successful_diagnostic_count += 1

            elif status == "failed":
                if diagnostic.get("method_used") is not None:
                    valid = False
                    break

                if diagnostic.get("fallback_used") is not False:
                    valid = False
                    break

                errors = diagnostic.get("errors")

                if (
                    not isinstance(
                        errors,
                        list,
                    )
                    or not errors
                ):
                    valid = False
                    break

            else:
                valid = False
                break

        if not valid:
            continue

        if successful_diagnostic_count == 0:
            continue

        # Every attempted country/metric forecast series
        # should have a corresponding diagnostic.
        if set(diagnostics_by_series) != expected_series:
            continue

        # The profile comparison requires every profile
        # metric to have at least one usable forecast
        # among the selected countries.
        successful_metrics = {
            metric_id
            for (
                _country_code,
                metric_id,
            ), diagnostic in diagnostics_by_series.items()
            if diagnostic.get("status")
            in {
                "ok",
                "warning",
            }
        }

        if successful_metrics != set(metric_ids):
            continue

        summary = envelope.get("summary")

        if not isinstance(
            summary,
            dict,
        ):
            continue

        if summary.get("selected_forecast_horizon") != forecast_horizon:
            continue

        metadata = summary.get("metadata")

        if not isinstance(
            metadata,
            dict,
        ):
            continue

        selected_years = metadata.get("selected_prediction_years")

        if (
            not isinstance(
                selected_years,
                list,
            )
            or not selected_years
        ):
            continue

        return (
            selected_countries,
            profile_name,
            metric_ids,
            method,
            horizon_years,
            forecast_horizon,
            envelope,
        )

    pytest.fail(
        "Could not find a release-dataset "
        "profile with a small country set "
        "suitable for the deterministic UI-10 "
        "predicted profile comparison case."
    )


def _find_countries_covering_profile(
    *,
    country_codes: list[str],
    metric_ids: list[str],
    method: str,
    horizon_years: int,
) -> list[str] | None:
    required_metrics = set(metric_ids)

    preferred_order = [
        "ARG",
        "BRA",
        "CHL",
        "COL",
        "MEX",
        "PER",
        "URY",
        "CRI",
        "PAN",
        "TUR",
        "ZAF",
        "MYS",
        "THA",
        "IDN",
        "PHL",
        "IND",
        "POL",
        "PRT",
        "ESP",
        "FRA",
        "DEU",
        "GBR",
        "USA",
        "CAN",
        "AUS",
        "JPN",
        "KOR",
        "NLD",
        "SWE",
        "CHE",
    ]

    available = set(country_codes)

    ordered_countries = [
        country_code for country_code in preferred_order if country_code in available
    ]

    ordered_countries.extend(
        country_code
        for country_code in country_codes
        if country_code not in ordered_countries
    )

    accumulated_coverage: dict[
        str,
        set[str],
    ] = {}

    batch_size = 20

    # Broaden beyond the previous 80-country search.
    search_limit = min(
        len(ordered_countries),
        120,
    )

    for start in range(
        0,
        search_limit,
        batch_size,
    ):
        batch = ordered_countries[start : start + batch_size]

        batch_coverage = _profile_prediction_coverage_for_countries(
            country_codes=batch,
            metric_ids=metric_ids,
            method=method,
            horizon_years=horizon_years,
        )

        accumulated_coverage.update(batch_coverage)

        total_coverage: set[str] = set()

        for covered_metrics in accumulated_coverage.values():
            total_coverage.update(covered_metrics)

        # There is no point attempting set-cover yet
        # if the searched countries collectively do not
        # cover the whole profile.
        if not required_metrics.issubset(total_coverage):
            continue

        remaining = {
            country_code: set(covered_metrics)
            for country_code, covered_metrics in accumulated_coverage.items()
            if covered_metrics
        }

        uncovered = set(required_metrics)
        selected: list[str] = []

        # Greedy set cover. The E2E case does not need
        # the mathematically smallest country set; it
        # only needs a small deterministic valid one.
        while uncovered and len(selected) < 6:
            best_country: str | None = None
            best_gain: set[str] = set()

            for (
                country_code,
                covered_metrics,
            ) in remaining.items():
                gain = covered_metrics & uncovered

                if len(gain) > len(best_gain):
                    best_country = country_code
                    best_gain = gain

            if best_country is None or not best_gain:
                break

            selected.append(best_country)

            uncovered.difference_update(best_gain)

            remaining.pop(
                best_country,
                None,
            )

        if uncovered:
            # More candidate countries may allow a
            # smaller/better coverage set.
            continue

        # Predicted comparison should remain an actual
        # comparison, not a one-country normalization.
        if len(selected) == 1:
            second_country = max(
                (
                    (
                        len(covered_metrics),
                        country_code,
                    )
                    for (
                        country_code,
                        covered_metrics,
                    ) in remaining.items()
                    if covered_metrics
                ),
                default=None,
            )

            if second_country is None:
                continue

            selected.append(second_country[1])

        return selected

    return None


def _prediction_diagnostics_by_series(
    diagnostics: dict[str, object],
) -> dict[
    tuple[str, str],
    dict[str, object],
]:
    items = diagnostics.get("items")
    assert isinstance(items, list)

    result: dict[
        tuple[str, str],
        dict[str, object],
    ] = {}

    for item in items:
        assert isinstance(item, dict)

        country_code = item.get("country_code")
        metric_id = item.get("metric_id")

        assert isinstance(country_code, str)
        assert country_code

        assert isinstance(metric_id, str)
        assert metric_id

        key = (
            country_code,
            metric_id,
        )

        assert key not in result
        result[key] = dict(item)

    return result


def _profile_prediction_coverage_for_countries(
    *,
    country_codes: list[str],
    metric_ids: list[str],
    method: str,
    horizon_years: int,
) -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {
        country_code: set() for country_code in country_codes
    }

    for metric_id in metric_ids:
        status_code, envelope = _api_post_json(
            "/api/v1/prediction/single-metric",
            {
                "country_codes": country_codes,
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

        if envelope.get("ok") is not True:
            continue

        try:
            diagnostics = _prediction_diagnostic_items(envelope)
        except AssertionError:
            continue

        for diagnostic in diagnostics:
            country_code = diagnostic.get("country_code")

            if not isinstance(country_code, str):
                continue

            if country_code not in coverage:
                continue

            status = diagnostic.get("status")

            if status not in {"ok", "warning"}:
                continue

            if diagnostic.get("method_used") != method:
                continue

            if diagnostic.get("fallback_used") is not False:
                continue

            coverage[country_code].add(metric_id)

    return coverage


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
    metric = page.locator('[data-testid="stMetric"]').filter(has_text=label).first

    expect(metric).to_be_visible(timeout=20_000)
    expect(metric).to_contain_text(label)
    expect(metric).to_contain_text(_ui_metric_value(value))


def _streamlit_metric_text(
    page: Page,
    *,
    label: str,
    occurrence: int = 0,
) -> str:
    metrics = page.locator('[data-testid="stMetric"]').filter(has_text=label)

    metric = metrics.nth(occurrence)

    expect(metric).to_be_visible(timeout=20_000)

    return metric.locator('[data-testid="stMetricValue"]').inner_text().strip()


def _assert_streamlit_error(
    page: Page,
    *,
    title: str,
    message: str,
) -> None:
    expected_text = f"{title}: {message}"

    alert = page.locator('[data-testid="stAlert"]').filter(has_text=expected_text).first

    expect(alert).to_be_visible(timeout=20_000)
    expect(alert).to_contain_text(expected_text)


def _select_streamlit_combobox_option(
    page: Page,
    *,
    label: str,
    option: str,
) -> None:
    combobox = page.get_by_role(
        "combobox",
        name=label,
        exact=True,
    )

    expect(combobox).to_be_visible(timeout=20_000)

    combobox.click()

    option_locator = page.get_by_role(
        "option",
        name=option,
        exact=True,
    )

    expect(option_locator).to_be_visible(timeout=20_000)

    option_locator.click()

    expect(combobox).to_have_value(
        option,
        timeout=20_000,
    )


def _assert_numeric_streamlit_metric(
    page: Page,
    *,
    label: str,
    expected: object,
    occurrence: int = 0,
) -> None:
    actual_text = _streamlit_metric_text(
        page,
        label=label,
        occurrence=occurrence,
    )

    assert actual_text != "—"

    actual_value = float(actual_text.replace(",", ""))

    expected_value = float(expected)

    assert actual_value == pytest.approx(expected_value)


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

    api_table = _main_table_dataframe(api_envelope)

    assert set(api_table["metric_id"].astype(str)) == set(metric_ids)

    expected_table = _expected_multi_metric_ui_table(api_table)

    expected_csv = _csv_bytes(expected_table)

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

    expect(run_button).to_be_visible(timeout=20_000)

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

    api_table = _main_table_dataframe(api_envelope)

    required_columns = {
        "country_code",
        "weighted_score",
        "score_rank",
    }

    assert required_columns.issubset(api_table.columns)

    for column in (
        "metric_count_used",
        "metric_count_expected",
        "weight_sum_used",
    ):
        assert column in api_table.columns

    expected_table = _expected_weighted_score_ui_table(api_table)

    expected_csv = _csv_bytes(expected_table)
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

    expect(run_button).to_be_visible(timeout=20_000)

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

    expected_table = _expected_forecast_ui_table(api_envelope)
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(expected_diagnostics, dict)

    expected_items = expected_diagnostics.get("items")
    assert isinstance(expected_items, list)
    assert len(expected_items) == 1

    expected_diagnostic = expected_items[0]
    assert isinstance(expected_diagnostic, dict)

    assert expected_diagnostic["method_requested"] == method
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

    expect(run_button).to_be_visible(timeout=20_000)

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

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    actual_diagnostics = actual_summary.get("diagnostics")

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

    expected_table = _expected_forecast_ui_table(api_envelope)
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(expected_diagnostics, dict)

    expected_by_country = _prediction_diagnostics_by_country(expected_diagnostics)

    assert set(expected_by_country) == set(country_codes)

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

    expect(run_button).to_be_visible(timeout=20_000)

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

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(actual_diagnostics, dict)

    actual_by_country = _prediction_diagnostics_by_country(actual_diagnostics)

    assert actual_by_country == expected_by_country


@pytest.mark.e2e
def test_ui_08_predicted_single_metric_comparison_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        method,
        horizon_years,
        forecast_horizon,
        api_envelope,
    ) = _find_predicted_single_metric_reference_case()

    expected_table = _named_table_dataframe(
        api_envelope,
        "predicted_comparison",
    )
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    selected_forecast_year = expected_summary.get("selected_forecast_year")
    selected_forecast_horizon = expected_summary.get("selected_forecast_horizon")

    assert selected_forecast_year is None or isinstance(selected_forecast_year, int)

    assert selected_forecast_horizon == forecast_horizon

    expected_metadata = expected_summary.get("metadata")
    assert isinstance(expected_metadata, dict)

    expected_prediction_years = expected_metadata.get("selected_prediction_years")
    assert isinstance(expected_prediction_years, list)
    assert expected_prediction_years

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(expected_diagnostics, dict)

    page.goto(
        _prediction_url(
            mode="predicted_single_metric_comparison",
            countries=country_codes,
            metric=metric_id,
            method=method,
            horizon_years=horizon_years,
            forecast_horizon=forecast_horizon,
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
        "Predicted Comparison",
    )

    # Deep-link mode must restore the correct comparison type.
    single_metric_radio = page.get_by_role(
        "radio",
        name="Single Metric",
        exact=True,
    )

    expect(single_metric_radio).to_be_checked(timeout=20_000)

    run_button = page.get_by_role(
        "button",
        name="Run predicted comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    # Streamlit may restore the first visible tab after rerun.
    _select_prediction_tab(
        page,
        "Predicted Comparison",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Predicted comparison table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _assert_streamlit_metric(
        page,
        label="Rows",
        value=len(expected_table.index),
    )

    _assert_streamlit_metric(
        page,
        label="Forecast year",
        value=selected_forecast_year,
    )

    _assert_streamlit_metric(
        page,
        label="Forecast horizon",
        value=selected_forecast_horizon,
    )

    actual_csv = _download_table_csv(page)

    # Predicted comparison rows can retain prediction execution
    # metadata from the underlying forecast batch.
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

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    assert actual_summary.get("selected_forecast_year") == selected_forecast_year

    assert actual_summary.get("selected_forecast_horizon") == selected_forecast_horizon

    actual_metadata = actual_summary.get("metadata")
    assert isinstance(actual_metadata, dict)

    assert actual_metadata.get("selected_prediction_years") == expected_prediction_years

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(actual_diagnostics, dict)

    assert actual_diagnostics == expected_diagnostics


@pytest.mark.e2e
def test_ui_09_predicted_multi_metric_comparison_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_ids,
        method,
        horizon_years,
        forecast_horizon,
        api_envelope,
    ) = _find_predicted_multi_metric_reference_case()

    assert len(country_codes) == 2
    assert len(metric_ids) == 2

    expected_table = _named_table_dataframe(
        api_envelope,
        "predicted_comparison",
    )
    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    selected_forecast_year = expected_summary.get("selected_forecast_year")
    selected_forecast_horizon = expected_summary.get("selected_forecast_horizon")

    assert selected_forecast_year is None or isinstance(selected_forecast_year, int)

    assert selected_forecast_horizon == forecast_horizon

    expected_metadata = expected_summary.get("metadata")
    assert isinstance(expected_metadata, dict)

    expected_prediction_years = expected_metadata.get("selected_prediction_years")

    assert isinstance(
        expected_prediction_years,
        list,
    )
    assert expected_prediction_years

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(
        expected_diagnostics,
        dict,
    )

    expected_by_series = _prediction_diagnostics_by_series(expected_diagnostics)

    expected_series = {
        (country_code, metric_id)
        for country_code in country_codes
        for metric_id in metric_ids
    }

    assert set(expected_by_series) == expected_series

    for diagnostic in expected_by_series.values():
        assert diagnostic["method_requested"] == method
        assert diagnostic["method_used"] == method
        assert diagnostic["fallback_used"] is False

    # Prove the API reference result itself contains
    # exactly one comparison row per country/metric pair.
    actual_pairs = {
        (
            str(row.country_code),
            str(row.metric_id),
        )
        for row in expected_table.itertuples(index=False)
    }

    assert actual_pairs == expected_series

    assert expected_table["value"].notna().all()

    assert expected_table["normalized_value"].notna().all()

    assert expected_table["rank"].notna().all()

    page.goto(
        _prediction_url(
            mode="predicted_multi_metric_comparison",
            countries=country_codes,
            metrics=metric_ids,
            method=method,
            horizon_years=horizon_years,
            forecast_horizon=forecast_horizon,
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
        "Predicted Comparison",
    )

    multi_metric_radio = page.get_by_role(
        "radio",
        name="Multi Metric",
        exact=True,
    )

    expect(multi_metric_radio).to_be_checked(timeout=20_000)

    run_button = page.get_by_role(
        "button",
        name="Run predicted comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    _select_prediction_tab(
        page,
        "Predicted Comparison",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Predicted comparison table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    _assert_streamlit_metric(
        page,
        label="Rows",
        value=len(expected_table.index),
    )

    _assert_streamlit_metric(
        page,
        label="Forecast year",
        value=selected_forecast_year,
    )

    _assert_streamlit_metric(
        page,
        label="Forecast horizon",
        value=selected_forecast_horizon,
    )

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

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    assert actual_summary.get("selected_forecast_year") == selected_forecast_year

    assert actual_summary.get("selected_forecast_horizon") == selected_forecast_horizon

    actual_metadata = actual_summary.get("metadata")
    assert isinstance(actual_metadata, dict)

    assert actual_metadata.get("selected_prediction_years") == expected_prediction_years

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(actual_diagnostics, dict)

    actual_by_series = _prediction_diagnostics_by_series(actual_diagnostics)

    assert actual_by_series == expected_by_series


@pytest.mark.e2e
def test_ui_10_predicted_profile_comparison_matches_backend_result(
    page: Page,
) -> None:
    (
        country_codes,
        profile_name,
        profile_metric_ids,
        method,
        horizon_years,
        forecast_horizon,
        api_envelope,
    ) = _find_predicted_profile_reference_case()

    assert 2 <= len(country_codes) <= 6
    assert len(set(country_codes)) == len(country_codes)
    assert profile_name
    assert profile_metric_ids

    expected_table = _named_table_dataframe(
        api_envelope,
        "predicted_comparison",
    )

    expected_csv = _csv_bytes(expected_table)

    required_profile_columns = {
        "country_code",
        "weighted_score",
        "score_rank",
        "profile_name",
    }

    assert required_profile_columns.issubset(expected_table.columns)

    assert expected_table["weighted_score"].notna().all()

    assert expected_table["score_rank"].notna().all()

    assert set(expected_table["profile_name"].astype(str).tolist()) == {profile_name}

    assert set(expected_table["country_code"].astype(str).tolist()) == set(
        country_codes
    )

    assert len(expected_table.index) == len(country_codes)

    rank_values = pd.to_numeric(
        expected_table["score_rank"],
        errors="raise",
    )

    top_index = rank_values.idxmin()
    top_row = expected_table.loc[top_index]

    expected_top_result = str(top_row.get("country_name") or top_row["country_code"])

    expected_top_value = float(top_row["weighted_score"])

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    selected_forecast_year = expected_summary.get("selected_forecast_year")

    selected_forecast_horizon = expected_summary.get("selected_forecast_horizon")

    assert selected_forecast_year is None or isinstance(selected_forecast_year, int)

    assert selected_forecast_horizon == forecast_horizon

    expected_metadata = expected_summary.get("metadata")
    assert isinstance(expected_metadata, dict)

    expected_prediction_years = expected_metadata.get("selected_prediction_years")

    assert isinstance(
        expected_prediction_years,
        list,
    )
    assert expected_prediction_years

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(
        expected_diagnostics,
        dict,
    )

    expected_by_series = _prediction_diagnostics_by_series(expected_diagnostics)

    expected_series = {
        (country_code, metric_id)
        for country_code in country_codes
        for metric_id in profile_metric_ids
    }

    assert set(expected_by_series) == expected_series

    successful_series_count = 0
    failed_series_count = 0

    for diagnostic in expected_by_series.values():
        assert diagnostic["method_requested"] == method

        status = diagnostic["status"]

        if status in {"ok", "warning"}:
            assert diagnostic["method_used"] == method
            assert diagnostic["fallback_used"] is False

            successful_series_count += 1

        else:
            assert status == "failed"
            assert diagnostic["method_used"] is None
            assert diagnostic["fallback_used"] is False
            assert diagnostic["errors"]

            failed_series_count += 1

    assert successful_series_count > 0
    assert successful_series_count + failed_series_count == len(expected_series)

    page.goto(
        _prediction_url(
            mode="predicted_profile_comparison",
            countries=country_codes,
            profile=profile_name,
            method=method,
            horizon_years=horizon_years,
            forecast_horizon=forecast_horizon,
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
        "Predicted Comparison",
    )

    profile_radio = page.get_by_role(
        "radio",
        name="Profile",
        exact=True,
    )

    expect(profile_radio).to_be_checked(timeout=20_000)

    run_button = page.get_by_role(
        "button",
        name="Run predicted comparison",
        exact=True,
    )

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    _select_prediction_tab(
        page,
        "Predicted Comparison",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Predicted comparison table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    expect(
        page.get_by_role(
            "heading",
            name="Ranked comparison summary",
            exact=True,
        )
    ).to_be_visible(timeout=20_000)

    _assert_streamlit_metric(
        page,
        label="Ranked rows",
        value=len(expected_table.index),
    )

    _assert_streamlit_metric(
        page,
        label="Top result",
        value=expected_top_result,
    )

    _assert_streamlit_metric(
        page,
        label="Top value",
        value=expected_top_value,
    )

    _assert_streamlit_metric(
        page,
        label="Rows",
        value=len(expected_table.index),
    )

    _assert_streamlit_metric(
        page,
        label="Forecast year",
        value=selected_forecast_year,
    )

    _assert_streamlit_metric(
        page,
        label="Forecast horizon",
        value=selected_forecast_horizon,
    )

    actual_csv = _download_table_csv(page)

    # The comparison table normally preserves the
    # prediction execution metadata. Validate it when
    # present, but don't require aggregate/profile
    # implementations to expose those columns.
    if all(
        column in expected_table.columns for column in _PREDICTION_RUN_SPECIFIC_COLUMNS
    ):
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

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    assert actual_summary.get("selected_forecast_year") == selected_forecast_year

    assert actual_summary.get("selected_forecast_horizon") == selected_forecast_horizon

    actual_metadata = actual_summary.get("metadata")
    assert isinstance(actual_metadata, dict)

    assert actual_metadata.get("selected_prediction_years") == expected_prediction_years

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(actual_diagnostics, dict)

    actual_by_series = _prediction_diagnostics_by_series(actual_diagnostics)

    assert actual_by_series == expected_by_series


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

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(expected_diagnostics, dict)

    assert expected_metrics["method_used"] == method
    assert expected_metrics["fallback_used"] is False
    assert expected_metrics["mae"] is not None
    assert expected_metrics["rmse"] is not None
    assert expected_metrics["mape"] is not None

    assert expected_metrics["n_test_observations"] == holdout_years

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

    expect(run_button).to_be_visible(timeout=20_000)
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

    assert actual_comparable_csv == expected_comparable_csv

    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    actual_metrics = actual_summary.get("metrics")
    assert isinstance(actual_metrics, dict)

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(actual_diagnostics, dict)

    assert actual_metrics == expected_metrics
    assert actual_diagnostics == expected_diagnostics


@pytest.mark.e2e
def test_ui_12_comparison_chart_ready_data_matches_result_table() -> None:
    result_table = pd.DataFrame(
        [
            {
                "country_name": "Gamma",
                "value": 30.5,
                "rank": 3,
            },
            {
                "country_name": "Alpha",
                "value": 10.25,
                "rank": 1,
            },
            {
                "country_name": "Beta",
                "value": 20.75,
                "rank": 2,
            },
        ]
    )

    expected_chart_data = pd.DataFrame(
        {
            "value": [
                10.25,
                20.75,
                30.5,
            ],
        },
        index=[
            "Alpha",
            "Beta",
            "Gamma",
        ],
    )

    actual_chart_data = build_comparison_chart_dataframe(result_table)

    pd.testing.assert_frame_equal(
        actual_chart_data,
        expected_chart_data,
        check_dtype=False,
    )


@pytest.mark.e2e
def test_ui_12_multi_metric_chart_ready_data_matches_result_table() -> None:
    result_table = pd.DataFrame(
        [
            {
                "country_name": "Alpha",
                "metric_name": "Metric A",
                "value": 10.0,
            },
            {
                "country_name": "Alpha",
                "metric_name": "Metric B",
                "value": 100.0,
            },
            {
                "country_name": "Beta",
                "metric_name": "Metric A",
                "value": 20.0,
            },
            {
                "country_name": "Beta",
                "metric_name": "Metric B",
                "value": 80.0,
            },
            {
                "country_name": "Gamma",
                "metric_name": "Metric A",
                "value": 15.0,
            },
            {
                "country_name": "Gamma",
                "metric_name": "Metric B",
                "value": 90.0,
            },
        ]
    )

    # Production ordering is by the mean plotted value:
    #
    # Alpha = 55.0
    # Gamma = 52.5
    # Beta  = 50.0
    #
    # The important oracle values themselves come
    # directly and independently from result_table.
    expected_chart_data = pd.DataFrame(
        {
            "Metric A": [
                10.0,
                15.0,
                20.0,
            ],
            "Metric B": [
                100.0,
                90.0,
                80.0,
            ],
        },
        index=[
            "Alpha",
            "Gamma",
            "Beta",
        ],
    )

    actual_chart_data = build_multi_metric_comparison_chart_dataframe(result_table)

    pd.testing.assert_frame_equal(
        actual_chart_data,
        expected_chart_data,
        check_dtype=False,
        check_names=False,
    )


@pytest.mark.e2e
def test_ui_12_predicted_comparison_chart_ready_data_matches_result_table() -> None:
    result_table = pd.DataFrame(
        [
            {
                "country_name": "Gamma",
                "weighted_score": 0.40,
                "score_rank": 3,
            },
            {
                "country_name": "Alpha",
                "weighted_score": 0.90,
                "score_rank": 1,
            },
            {
                "country_name": "Beta",
                "weighted_score": 0.60,
                "score_rank": 2,
            },
        ]
    )

    expected_chart_data = pd.DataFrame(
        {
            "weighted_score": [
                0.90,
                0.60,
                0.40,
            ],
        },
        index=[
            "Alpha",
            "Beta",
            "Gamma",
        ],
    )

    actual_chart_data = build_predicted_comparison_chart_dataframe(result_table)

    pd.testing.assert_frame_equal(
        actual_chart_data,
        expected_chart_data,
        check_dtype=False,
    )


@pytest.mark.e2e
def test_ui_12_backtest_chart_ready_data_matches_result_table() -> None:
    result_table = pd.DataFrame(
        [
            {
                "year": 2024,
                "actual_value": 30.0,
                "predicted_value": 31.25,
            },
            {
                "year": 2022,
                "actual_value": 10.0,
                "predicted_value": 11.50,
            },
            {
                "year": 2023,
                "actual_value": 20.0,
                "predicted_value": 19.75,
            },
        ]
    )

    expected_chart_data = pd.DataFrame(
        {
            "Actual": [
                10.0,
                20.0,
                30.0,
            ],
            "Predicted": [
                11.50,
                19.75,
                31.25,
            ],
        },
        index=[
            2022,
            2023,
            2024,
        ],
    )

    actual_chart_data = build_backtest_line_chart_dataframe(result_table)

    pd.testing.assert_frame_equal(
        actual_chart_data,
        expected_chart_data,
        check_dtype=False,
    )


@pytest.mark.e2e
def test_ui_12_forecast_chart_ready_data_matches_result_table() -> None:
    result_table = pd.DataFrame(
        [
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "metric_a",
                "metric_name": "Metric A",
                "year": 2022,
                "value": 10.0,
                "row_type": "actual",
            },
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "metric_a",
                "metric_name": "Metric A",
                "year": 2023,
                "value": 20.0,
                "row_type": "actual",
            },
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "metric_a",
                "metric_name": "Metric A",
                "year": 2024,
                "value": 30.5,
                "row_type": "predicted",
                "forecast_horizon": 1,
            },
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "metric_a",
                "metric_name": "Metric A",
                "year": 2025,
                "value": 40.75,
                "row_type": "predicted",
                "forecast_horizon": 2,
            },
        ]
    )

    # build_line_chart_dataframe() only needs an
    # object exposing combined_df.
    prediction_result = SimpleNamespace(combined_df=result_table)

    renderer_neutral_data = build_line_chart_dataframe(prediction_result)

    actual_chart_data = build_streamlit_line_chart_table(renderer_neutral_data)

    expected_chart_data = pd.DataFrame(
        {
            "Alpha actual": [
                10.0,
                20.0,
                float("nan"),
                float("nan"),
            ],
            "Alpha forecast": [
                float("nan"),
                float("nan"),
                30.5,
                40.75,
            ],
        },
        index=pd.Index(
            pd.array(
                [
                    2022,
                    2023,
                    2024,
                    2025,
                ],
                dtype="Int64",
            ),
            name="year",
        ),
    )

    pd.testing.assert_frame_equal(
        actual_chart_data,
        expected_chart_data,
        check_dtype=False,
        check_names=False,
    )


@pytest.mark.e2e
def test_ui_13_single_metric_summary_matches_first_ranked_row(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        api_envelope,
    ) = _find_single_metric_reference_case()

    table = _main_table_dataframe(api_envelope)

    required_columns = {
        "country_code",
        "rank",
        "value",
    }

    assert required_columns.issubset(table.columns)

    ranks = pd.to_numeric(
        table["rank"],
        errors="raise",
    )

    top_index = ranks.idxmin()
    top_row = table.loc[top_index]

    top_country = str(top_row.get("country_name") or top_row["country_code"])

    top_rank = top_row["rank"]
    top_value = top_row["value"]

    assert float(top_rank) == pytest.approx(1.0)

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

    assert (
        _streamlit_metric_text(
            page,
            label="Top item",
        )
        == top_country
    )

    _assert_numeric_streamlit_metric(
        page,
        label="Top rank",
        expected=top_rank,
    )

    _assert_numeric_streamlit_metric(
        page,
        label="Top value",
        expected=top_value,
        occurrence=0,
    )


@pytest.mark.e2e
def test_ui_13_weighted_score_summary_matches_first_ranked_row(
    page: Page,
) -> None:
    (
        country_codes,
        profile_name,
        api_envelope,
    ) = _find_weighted_score_reference_case()

    table = _main_table_dataframe(api_envelope)

    required_columns = {
        "country_code",
        "weighted_score",
        "score_rank",
    }

    assert required_columns.issubset(table.columns)

    ranks = pd.to_numeric(
        table["score_rank"],
        errors="raise",
    )

    top_index = ranks.idxmin()
    top_row = table.loc[top_index]

    top_country = str(top_row.get("country_name") or top_row["country_code"])

    top_rank = top_row["score_rank"]

    top_value = top_row["weighted_score"]

    assert float(top_rank) == pytest.approx(1.0)

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

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    _select_compare_tab(
        page,
        "Weighted Score",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    assert (
        _streamlit_metric_text(
            page,
            label="Top item",
        )
        == top_country
    )

    _assert_numeric_streamlit_metric(
        page,
        label="Top rank",
        expected=top_rank,
    )

    _assert_numeric_streamlit_metric(
        page,
        label="Top value",
        expected=top_value,
        occurrence=0,
    )


@pytest.mark.e2e
def test_ui_13_multi_metric_summary_matches_documented_logic(
    page: Page,
) -> None:
    (
        country_codes,
        metric_ids,
        api_envelope,
    ) = _find_multi_metric_reference_case()

    table = _main_table_dataframe(api_envelope)

    required_columns = {
        "country_code",
        "normalized_value",
        "metric_id",
    }

    assert required_columns.issubset(table.columns)

    grouping_columns = [
        "country_code",
    ]

    if "country_name" in table.columns:
        grouping_columns.append("country_name")

    working = table.copy()

    working["normalized_value"] = pd.to_numeric(
        working["normalized_value"],
        errors="raise",
    )

    summary = (
        working.groupby(
            grouping_columns,
            dropna=False,
        )["normalized_value"]
        .mean()
        .sort_values(ascending=False)
        .reset_index()
    )

    assert not summary.empty

    top_row = summary.iloc[0]

    top_country = str(top_row.get("country_name") or top_row["country_code"])

    returned_metric_count = table["metric_id"].astype(str).nunique()

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

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    _select_compare_tab(
        page,
        "Multi Metric",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    assert (
        _streamlit_metric_text(
            page,
            label="Top item",
        )
        == top_country
    )

    assert (
        _streamlit_metric_text(
            page,
            label="Top rank",
        )
        == "—"
    )

    _assert_numeric_streamlit_metric(
        page,
        label="Top value",
        expected=returned_metric_count,
        occurrence=0,
    )


def _find_ui_14_diagnostic_reference_case() -> tuple[
    list[str],
    str,
    str,
    int,
    dict[str, object],
]:
    method = "holt_linear"
    fallback_method = "last_observed"
    horizon_years = 3

    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)

    country_codes = [
        str(item.get("code") or item.get("country_code") or "").strip().upper()
        for item in countries
        if isinstance(item, dict)
    ]

    metric_ids = [
        str(item.get("metric_id") or item.get("id") or "").strip()
        for item in metrics
        if isinstance(item, dict)
    ]

    country_codes = [value for value in country_codes if value]
    metric_ids = [value for value in metric_ids if value]

    batch_size = 10

    for metric_id in metric_ids:
        fallback_country: str | None = None
        failed_country: str | None = None

        for start in range(
            0,
            len(country_codes),
            batch_size,
        ):
            batch = country_codes[start : start + batch_size]

            status_code, envelope = _api_post_json(
                "/api/v1/prediction/single-metric",
                {
                    "country_codes": batch,
                    "metric_id": metric_id,
                    "horizon_years": horizon_years,
                    "method": method,
                    "fallback_method": (fallback_method),
                    "fail_fast": False,
                    "scenario_id": "baseline",
                },
            )

            if status_code != 200:
                continue

            if envelope.get("ok") is not True:
                continue

            try:
                diagnostics = _prediction_diagnostic_items(envelope)
            except AssertionError:
                continue

            for diagnostic in diagnostics:
                country_code = diagnostic.get("country_code")

                if not isinstance(
                    country_code,
                    str,
                ):
                    continue

                if (
                    fallback_country is None
                    and diagnostic.get("status") == "warning"
                    and diagnostic.get("method_requested") == method
                    and diagnostic.get("method_used") == fallback_method
                    and diagnostic.get("fallback_used") is True
                    and diagnostic.get("warnings")
                ):
                    fallback_country = country_code

                if (
                    failed_country is None
                    and diagnostic.get("status") == "failed"
                    and diagnostic.get("method_requested") == method
                    and diagnostic.get("errors")
                ):
                    failed_country = country_code

            if fallback_country is not None and failed_country is not None:
                break

        if (
            fallback_country is None
            or failed_country is None
            or fallback_country == failed_country
        ):
            continue

        selected_countries = [
            fallback_country,
            failed_country,
        ]

        status_code, final_envelope = _api_post_json(
            "/api/v1/prediction/single-metric",
            {
                "country_codes": (selected_countries),
                "metric_id": metric_id,
                "horizon_years": (horizon_years),
                "method": method,
                "fallback_method": (fallback_method),
                "fail_fast": False,
                "scenario_id": "baseline",
            },
        )

        if status_code != 200:
            continue

        if final_envelope.get("ok") is not True:
            continue

        diagnostics = _prediction_diagnostic_items(final_envelope)

        fallback_items = [
            item
            for item in diagnostics
            if (
                item.get("country_code") == fallback_country
                and item.get("status") == "warning"
                and item.get("method_used") == fallback_method
                and item.get("fallback_used") is True
            )
        ]

        failed_items = [
            item
            for item in diagnostics
            if (
                item.get("country_code") == failed_country
                and item.get("status") == "failed"
                and item.get("errors")
            )
        ]

        if len(fallback_items) == 1 and len(failed_items) == 1:
            return (
                selected_countries,
                metric_id,
                method,
                horizon_years,
                final_envelope,
            )

    pytest.fail(
        "Could not find a release-dataset "
        "UI-14 case containing both a "
        "fallback series and a failed series."
    )


@pytest.mark.e2e
def test_ui_14_prediction_limitations_are_visible(
    page: Page,
) -> None:
    (
        country_code,
        metric_id,
        method,
        horizon_years,
        _api_envelope,
    ) = _find_single_forecast_reference_case()

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

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    # Streamlit reruns can restore the
    # first visible tab.
    _select_prediction_tab(
        page,
        "Single Forecast",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Prediction quality",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    limitations = _open_streamlit_expander(
        page,
        "Prediction limitations",
    )

    for limitation in _UI_14_BASE_PREDICTION_LIMITATIONS:
        expect(limitations).to_contain_text(limitation)


@pytest.mark.e2e
def test_ui_14_warnings_fallback_and_failed_series_are_visible(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        method,
        horizon_years,
        api_envelope,
    ) = _find_ui_14_diagnostic_reference_case()

    assert len(country_codes) == 2

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(
        expected_diagnostics,
        dict,
    )

    diagnostic_items = _prediction_diagnostic_items(api_envelope)

    fallback_items = [
        item
        for item in diagnostic_items
        if (item.get("status") == "warning" and item.get("fallback_used") is True)
    ]

    failed_items = [item for item in diagnostic_items if item.get("status") == "failed"]

    assert len(fallback_items) == 1
    assert len(failed_items) == 1

    fallback_diagnostic = fallback_items[0]
    failed_diagnostic = failed_items[0]

    fallback_country = fallback_diagnostic["country_code"]
    failed_country = failed_diagnostic["country_code"]

    assert isinstance(
        fallback_country,
        str,
    )
    assert isinstance(
        failed_country,
        str,
    )

    assert fallback_diagnostic["method_requested"] == method
    assert fallback_diagnostic["method_used"] == "last_observed"
    assert fallback_diagnostic["fallback_used"] is True

    fallback_warnings = fallback_diagnostic.get("warnings")
    assert isinstance(
        fallback_warnings,
        list,
    )
    assert fallback_warnings

    failed_errors = failed_diagnostic.get("errors")
    assert isinstance(failed_errors, list)
    assert failed_errors

    expected_warnings = api_envelope.get("warnings")
    assert isinstance(expected_warnings, list)
    assert expected_warnings

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

    expect(run_button).to_be_visible(timeout=20_000)

    run_button.click()

    _select_prediction_tab(
        page,
        "Multi-Country Forecast",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Prediction quality",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    # Result-level warnings from the API
    # must remain visible in the UI.
    for warning in expected_warnings:
        warning_alert = (
            page.locator('[data-testid="stAlert"]').filter(has_text=str(warning)).first
        )

        expect(warning_alert).to_be_visible(timeout=20_000)

    _assert_streamlit_metric(
        page,
        label="Failed series",
        value=1,
    )

    _assert_streamlit_metric(
        page,
        label="Failed",
        value=1,
    )

    # The downloadable diagnostics give us
    # exact API -> browser-result parity.
    actual_diagnostics_payload = _download_diagnostics_json(page)

    actual_summary = actual_diagnostics_payload.get("summary")
    assert isinstance(actual_summary, dict)

    actual_diagnostics = actual_summary.get("diagnostics")
    assert isinstance(
        actual_diagnostics,
        dict,
    )

    assert actual_diagnostics == expected_diagnostics

    # Also prove that the human-visible
    # Diagnostics panel attributes the
    # fallback and failure correctly.
    diagnostics_expander = _open_streamlit_expander(
        page,
        "Diagnostics",
    )

    expect(diagnostics_expander).to_contain_text(fallback_country)

    expect(diagnostics_expander).to_contain_text(failed_country)

    expect(diagnostics_expander).to_contain_text(metric_id)

    expect(diagnostics_expander).to_contain_text(method)

    expect(diagnostics_expander).to_contain_text("last_observed")

    for warning in fallback_warnings:
        expect(diagnostics_expander).to_contain_text(str(warning))

    for error in failed_errors:
        assert isinstance(error, dict)

        error_code = error.get("code")
        error_message = error.get("message")

        if error_code:
            expect(diagnostics_expander).to_contain_text(str(error_code))

        if error_message:
            expect(diagnostics_expander).to_contain_text(str(error_message))


@pytest.mark.e2e
def test_ui_15_comparison_exports_preserve_api_result(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        api_envelope,
    ) = _find_single_metric_reference_case()

    api_table = _main_table_dataframe(api_envelope)

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

    csv_payload = _download_table_csv(page)
    json_payload = _download_diagnostics_json(page)
    markdown_payload = _download_summary_markdown(page)

    _assert_export_csv_matches_api_columns(
        csv_payload=csv_payload,
        api_table=api_table,
        sort_columns=(
            "rank",
            "country_code",
        ),
    )

    assert json_payload.get("mode") == api_envelope.get("mode")

    metadata = json_payload.get("metadata")
    assert isinstance(metadata, dict)

    selection = metadata.get("Selection")
    assert isinstance(selection, dict)

    assert selection.get("Metric ID") == metric_id
    assert selection.get("Countries") == country_codes

    data_metadata = metadata.get("Data")
    assert isinstance(data_metadata, dict)

    assert data_metadata.get("Rows returned") == len(api_table.index)

    assert f"Rows: {len(api_table.index)}" in markdown_payload

    assert f"Columns: {len(api_table.columns)}" in markdown_payload

    _assert_exports_contain_no_secrets(
        csv_payload,
        json.dumps(
            json_payload,
            sort_keys=True,
        ),
        markdown_payload,
    )


@pytest.mark.e2e
def test_ui_15_scoring_exports_preserve_api_result(
    page: Page,
) -> None:
    (
        country_codes,
        profile_name,
        api_envelope,
    ) = _find_weighted_score_reference_case()

    api_table = _main_table_dataframe(api_envelope)

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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

    _select_compare_tab(
        page,
        "Weighted Score",
    )

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    csv_payload = _download_table_csv(page)
    json_payload = _download_diagnostics_json(page)
    markdown_payload = _download_summary_markdown(page)

    _assert_export_csv_matches_api_columns(
        csv_payload=csv_payload,
        api_table=api_table,
        sort_columns=(
            "score_rank",
            "country_code",
        ),
    )

    metadata = json_payload.get("metadata")
    assert isinstance(metadata, dict)

    selection = metadata.get("Selection")
    assert isinstance(selection, dict)

    assert selection.get("Profile") == profile_name
    assert selection.get("Countries") == country_codes

    data_metadata = metadata.get("Data")
    assert isinstance(data_metadata, dict)

    assert data_metadata.get("Rows returned") == len(api_table.index)

    assert f"Rows: {len(api_table.index)}" in markdown_payload

    _assert_exports_contain_no_secrets(
        csv_payload,
        json.dumps(
            json_payload,
            sort_keys=True,
        ),
        markdown_payload,
    )


@pytest.mark.e2e
def test_ui_15_prediction_exports_preserve_api_result(
    page: Page,
) -> None:
    (
        country_code,
        metric_id,
        method,
        horizon_years,
        api_envelope,
    ) = _find_single_forecast_reference_case()

    expected_table = _expected_forecast_ui_table(api_envelope)

    expected_csv = _csv_bytes(expected_table)

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_diagnostics = expected_summary.get("diagnostics")
    assert isinstance(
        expected_diagnostics,
        dict,
    )

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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

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

    csv_payload = _download_table_csv(page)
    json_payload = _download_diagnostics_json(page)
    markdown_payload = _download_summary_markdown(page)

    _assert_prediction_run_metadata(csv_payload)

    assert _csv_without_columns(
        csv_payload,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    ) == _csv_without_columns(
        expected_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    exported_summary = json_payload.get("summary")
    assert isinstance(exported_summary, dict)

    assert exported_summary.get("diagnostics") == expected_diagnostics

    assert "# Country Compare Prediction Result" in markdown_payload
    assert f"Rows: {len(expected_table.index)}" in markdown_payload
    assert f"Columns: {len(expected_table.columns)}" in markdown_payload

    _assert_exports_contain_no_secrets(
        csv_payload,
        json.dumps(
            json_payload,
            sort_keys=True,
        ),
        markdown_payload,
    )


@pytest.mark.e2e
def test_ui_15_backtest_exports_preserve_api_result(
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

    expected_summary = api_envelope.get("summary")
    assert isinstance(expected_summary, dict)

    expected_metrics = expected_summary.get("metrics")
    expected_diagnostics = expected_summary.get("diagnostics")

    assert isinstance(
        expected_metrics,
        dict,
    )
    assert isinstance(
        expected_diagnostics,
        dict,
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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

    _select_prediction_tab(
        page,
        "Backtest",
    )

    expect(
        page.get_by_text(
            "Actual vs predicted",
            exact=True,
        )
    ).to_be_visible(timeout=30_000)

    csv_payload = _download_table_csv(page)
    json_payload = _download_diagnostics_json(page)
    markdown_payload = _download_summary_markdown(page)

    expected_csv = _csv_bytes(expected_table)

    _assert_prediction_run_metadata(csv_payload)

    assert _csv_without_columns(
        csv_payload,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    ) == _csv_without_columns(
        expected_csv,
        _PREDICTION_RUN_SPECIFIC_COLUMNS,
    )

    assert json_payload.get("metrics") == expected_metrics

    exported_summary = json_payload.get("summary")
    assert isinstance(exported_summary, dict)

    assert exported_summary.get("diagnostics") == expected_diagnostics

    assert "# Country Compare Backtest Result" in markdown_payload

    _assert_exports_contain_no_secrets(
        csv_payload,
        json.dumps(
            json_payload,
            sort_keys=True,
        ),
        markdown_payload,
    )


@pytest.mark.e2e
def test_ui_15_llm_exports_are_safe_when_available(
    page: Page,
) -> None:
    if not _prediction_method_available("llm_forecast"):
        pytest.skip("llm_forecast is not advertised " "by this runtime.")

    (
        country_code,
        metric_id,
        _deterministic_method,
        _,
        _,
    ) = _find_single_forecast_reference_case()

    horizon_years = 1

    page.goto(
        _prediction_url(
            mode="single_forecast",
            country=country_code,
            metric=metric_id,
            method="llm_forecast",
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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

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
    ).to_be_visible(timeout=60_000)

    csv_payload = _download_table_csv(page)
    json_payload = _download_diagnostics_json(page)
    markdown_payload = _download_summary_markdown(page)

    dataframe = pd.read_csv(BytesIO(csv_payload))

    assert len(dataframe.index) == 1

    assert dataframe["country_code"].astype(str).eq(country_code).all()

    assert dataframe["metric_id"].astype(str).eq(metric_id).all()

    predicted_values = pd.to_numeric(
        dataframe["predicted_value"],
        errors="raise",
    )

    assert predicted_values.notna().all()

    exported_summary = json_payload.get("summary")
    assert isinstance(exported_summary, dict)

    diagnostics = exported_summary.get("diagnostics")
    assert isinstance(diagnostics, dict)

    items = diagnostics.get("items")
    assert isinstance(items, list)
    assert len(items) == 1

    item = items[0]
    assert isinstance(item, dict)

    assert item.get("method_requested") == "llm_forecast"
    assert item.get("method_used") == "llm_forecast"
    assert item.get("fallback_used") is False

    assert "# Country Compare Prediction Result" in markdown_payload

    _assert_exports_contain_no_secrets(
        csv_payload,
        json.dumps(
            json_payload,
            sort_keys=True,
        ),
        markdown_payload,
    )


@pytest.mark.e2e
def test_ui_16_single_metric_requires_two_countries(
    page: Page,
) -> None:
    (
        country_codes,
        metric_id,
        _api_envelope,
    ) = _find_single_metric_reference_case()

    assert country_codes

    page.goto(
        _compare_url(
            countries=[country_codes[0]],
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

    _assert_streamlit_error(
        page,
        title="Countries are required",
        message=("Please select at least two countries."),
    )

    # No successful result should have been
    # generated from the invalid request.
    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).not_to_be_visible()


@pytest.mark.e2e
def test_ui_16_multi_metric_requires_metric_selection(
    page: Page,
) -> None:
    (
        country_codes,
        _metric_ids,
        _api_envelope,
    ) = _find_multi_metric_reference_case()

    assert len(country_codes) >= 2

    page.goto(
        _compare_url(
            countries=country_codes,
            mode="multi_metric",
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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

    _select_compare_tab(
        page,
        "Multi Metric",
    )

    _assert_streamlit_error(
        page,
        title="Metrics are required",
        message=("Please select at least one metric " "before running the comparison."),
    )

    expect(
        page.get_by_role(
            "heading",
            name="Main result table",
            exact=True,
        )
    ).not_to_be_visible()


@pytest.mark.e2e
def test_ui_16_target_year_is_enabled_and_bounded_only_for_target_year_strategy(
    page: Page,
) -> None:
    countries_payload = _api_get_json("/api/v1/metadata/countries")
    metrics_payload = _api_get_json("/api/v1/metadata/metrics")
    years_payload = _api_get_json("/api/v1/metadata/years")

    countries = countries_payload.get("countries")
    metrics = metrics_payload.get("metrics")
    years = years_payload.get("years")

    assert isinstance(countries, list)
    assert isinstance(metrics, list)
    assert isinstance(years, list)
    assert len(countries) >= 2
    assert metrics
    assert years

    country_codes = [
        str(item.get("code") or item.get("country_code")) for item in countries[:2]
    ]

    metric_item = metrics[0]
    assert isinstance(metric_item, dict)

    metric_id = str(metric_item.get("metric_id") or metric_item.get("id"))

    min_year = min(int(year) for year in years)
    max_year = max(int(year) for year in years)

    page.goto(
        _compare_url(
            countries=country_codes,
            mode="single_metric",
            metric=metric_id,
        ),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    target_year = page.get_by_role(
        "spinbutton",
        name="Target year",
        exact=True,
    )

    expect(target_year).to_be_visible(timeout=20_000)
    expect(target_year).to_be_disabled()

    _select_streamlit_combobox_option(
        page,
        label="Year strategy",
        option="Target year",
    )

    expect(target_year).to_be_enabled(timeout=20_000)

    assert int(target_year.get_attribute("min") or min_year) == min_year

    assert int(target_year.get_attribute("max") or max_year) == max_year

    current_year = int(target_year.input_value())

    assert min_year <= current_year <= max_year


@pytest.mark.e2e
def test_ui_16_multi_country_prediction_requires_countries(
    page: Page,
) -> None:
    (
        _country_code,
        metric_id,
        method,
        horizon_years,
        _api_envelope,
    ) = _find_single_forecast_reference_case()

    page.goto(
        _prediction_url(
            mode="multi_country_forecast",
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

    expect(run_button).to_be_visible(timeout=20_000)
    run_button.click()

    _select_prediction_tab(
        page,
        "Multi-Country Forecast",
    )

    _assert_streamlit_error(
        page,
        title="Countries are required",
        message=("Please select at least one country " "before running the forecast."),
    )

    expect(
        page.get_by_role(
            "heading",
            name="Forecast table",
            exact=True,
        )
    ).not_to_be_visible()
