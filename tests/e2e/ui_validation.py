from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlencode

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

    expected_csv = expected_table.to_csv(
        index=False,
        lineterminator="\n",
    ).encode("utf-8")

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

    actual_csv = download_path.read_bytes()

    assert actual_csv == expected_csv
