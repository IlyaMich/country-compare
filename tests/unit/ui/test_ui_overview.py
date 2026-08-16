from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from country_compare.clients.base import CountryCompareClient
from country_compare.services.models import DatasetSummary
from country_compare.ui.runtime import (
    UiCapabilities,
    UiMode,
    UiRuntimeContext,
)
from country_compare.ui.views import overview as overview_view


class _FakeOverviewClient:
    mode = "http"

    def __init__(self, overview: object | None = None) -> None:
        self.overview = overview
        self.validate_config_against_dataset: bool | None = None
        self.countries_requested = False
        self.metrics_requested = False

    def get_overview_status(
        self,
        *,
        validate_config_against_dataset: bool = False,
    ) -> object:
        self.validate_config_against_dataset = validate_config_against_dataset
        return self.overview

    def list_countries(self) -> list[object]:
        self.countries_requested = True
        return []

    def list_metrics(self) -> list[object]:
        self.metrics_requested = True
        return []


def _runtime(
    *,
    fake_app_context,
    client: _FakeOverviewClient,
) -> UiRuntimeContext:
    return UiRuntimeContext(
        app_context=fake_app_context,
        client=cast(CountryCompareClient, client),
        mode=UiMode.HTTP,
        capabilities=UiCapabilities(config_editing=False),
    )


def test_render_page_uses_runtime_client(
    monkeypatch,
    fake_app_context,
) -> None:
    dataset = object()
    config = object()

    overview = SimpleNamespace(
        warnings=("remote warning",),
        dataset=dataset,
        config=config,
    )

    client = _FakeOverviewClient(overview=overview)
    runtime = _runtime(
        fake_app_context=fake_app_context,
        client=client,
    )

    rendered_dataset: list[object] = []
    rendered_config: list[object] = []

    monkeypatch.setattr(
        overview_view.st,
        "title",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "caption",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "checkbox",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        overview_view.st,
        "info",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "subheader",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "divider",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "write",
        lambda *args, **kwargs: None,
    )

    def render_dataset(
        value,
        *,
        client,
        debug,
    ) -> None:
        assert client is runtime.client
        assert debug is True
        rendered_dataset.append(value)

    def render_config(
        value,
        *,
        debug,
    ) -> None:
        assert debug is True
        rendered_config.append(value)

    monkeypatch.setattr(
        overview_view,
        "_render_dataset_section",
        render_dataset,
    )
    monkeypatch.setattr(
        overview_view,
        "_render_config_section",
        render_config,
    )

    overview_view.render_page(runtime, debug=True)

    assert client.validate_config_against_dataset is True
    assert rendered_dataset == [dataset]
    assert rendered_config == [config]


def test_dataset_section_loads_catalogs_through_client(
    monkeypatch,
) -> None:
    client = _FakeOverviewClient()

    dataset = DatasetSummary(
        exists=True,
        backend="parquet",
        dataset_path="/tmp/metrics.parquet",
        row_count=10,
        country_count=2,
        metric_count=3,
        year_min=2020,
        year_max=2025,
    )

    def columns(spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [Mock() for _ in range(count)]

    monkeypatch.setattr(overview_view.st, "columns", columns)
    monkeypatch.setattr(
        overview_view.st,
        "success",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "write",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "dataframe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        overview_view.st,
        "expander",
        lambda *args, **kwargs: nullcontext(),
    )

    overview_view._render_dataset_section(
        dataset,
        client=cast(CountryCompareClient, client),
        debug=False,
    )

    assert client.countries_requested is True
    assert client.metrics_requested is True
