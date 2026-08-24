from __future__ import annotations

import os
import re
from collections.abc import Iterator

import httpx
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
    sidebar = page.locator(
        '[data-testid="stSidebarContent"]'
    )

    radio = sidebar.get_by_role(
        "radio",
        name=label,
        exact=True,
    )

    expect(radio).to_be_visible()

    radio_label = radio.locator(
        "xpath=ancestor::label[1]"
    )

    expect(radio_label).to_be_visible()

    radio_label.click()

    expect(radio).to_be_checked(timeout=20_000)


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