from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from country_compare.pipelines.acquisition.snapshot import (
    NonRetryableSourceSnapshotAcquisitionError,
    RetryableSourceSnapshotAcquisitionError,
    SourceSnapshotAcquirer,
)
from country_compare.pipelines.acquisition.world_bank import (
    RetryableWorldBankAcquisitionError,
    WorldBankAcquisitionPlan,
    WorldBankIndicatorSnapshotAcquirer,
    build_world_bank_indicator_zip_url,
)


class FakeHttpResponse:
    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        self._buffer = BytesIO(payload)
        self.status = status

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        self._buffer.close()

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def test_build_world_bank_indicator_zip_url() -> None:
    url = build_world_bank_indicator_zip_url("NY.GDP.MKTP.CD")

    assert url == (
        "https://api.worldbank.org/v2/en/country/all/indicator/NY.GDP.MKTP.CD"
        "?source=2&downloadformat=csv"
    )


def test_build_world_bank_indicator_zip_url_encodes_indicator_code() -> None:
    url = build_world_bank_indicator_zip_url("A B")

    assert url == (
        "https://api.worldbank.org/v2/en/country/all/indicator/A%20B"
        "?source=2&downloadformat=csv"
    )


def test_remote_world_bank_snapshot_downloads_and_normalizes_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    payload = _world_bank_zip_payload("NY.GDP.MKTP.CD")
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        requested_urls.append(request.full_url)
        assert timeout == 60
        return FakeHttpResponse(payload)

    monkeypatch.setattr(
        "country_compare.pipelines.acquisition.world_bank.urlopen",
        fake_urlopen,
    )

    result = SourceSnapshotAcquirer(
        workspace_root=tmp_path / "work"
    ).acquire_manifest_sources(
        job_id="job_1",
        source_family="world_bank",
        manifest_path=manifest_path,
        acquisition_mode="remote",
    )

    assert requested_urls == [build_world_bank_indicator_zip_url("NY.GDP.MKTP.CD")]
    assert len(result.assets) == 1
    asset = result.assets[0]
    assert asset.source_id == "wb_gdp_current_usd"
    assert asset.indicator_code == "NY.GDP.MKTP.CD"
    assert asset.raw_archive_path == "archives/wb_gdp_current_usd.zip"
    assert asset.normalized_file_path == "raw/gdp_current_usd/wb_gdp_current_usd.csv"
    assert sorted(asset.metadata_paths) == sorted(
        [
            "metadata/wb_gdp_current_usd/wb_gdp_current_usd_country_metadata.csv",
            "metadata/wb_gdp_current_usd/wb_gdp_current_usd_indicator_metadata.csv",
        ]
    )
    assert Path(result.audit_path).exists()
    assert (Path(result.raw_dir) / "gdp_current_usd/wb_gdp_current_usd.csv").exists()


def test_remote_world_bank_snapshot_rejects_unsafe_zip_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    payload = _zip_payload({"../evil.csv": "bad"})

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        return FakeHttpResponse(payload)

    monkeypatch.setattr(
        "country_compare.pipelines.acquisition.world_bank.urlopen",
        fake_urlopen,
    )

    with pytest.raises(NonRetryableSourceSnapshotAcquisitionError, match="unsafe"):
        SourceSnapshotAcquirer(
            workspace_root=tmp_path / "work"
        ).acquire_manifest_sources(
            job_id="job_1",
            source_family="world_bank",
            manifest_path=manifest_path,
            acquisition_mode="remote",
        )


def test_remote_world_bank_snapshot_classifies_http_500_as_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from urllib.error import HTTPError

    manifest_path = _write_manifest(tmp_path)

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        raise HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr(
        "country_compare.pipelines.acquisition.world_bank.urlopen",
        fake_urlopen,
    )

    with pytest.raises(RetryableSourceSnapshotAcquisitionError, match="HTTP 500"):
        SourceSnapshotAcquirer(
            workspace_root=tmp_path / "work"
        ).acquire_manifest_sources(
            job_id="job_1",
            source_family="world_bank",
            manifest_path=manifest_path,
            acquisition_mode="remote",
        )


def test_download_zip_retries_retryable_http_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    destination = tmp_path / "source.zip"

    acquirer = WorldBankIndicatorSnapshotAcquirer(
        plan=WorldBankAcquisitionPlan(
            max_download_attempts=3,
            retry_backoff_seconds=0,
        )
    )

    def fake_download_once(url: str, destination: Path, *, source_id: str) -> None:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RetryableWorldBankAcquisitionError(
                f"World Bank returned retryable HTTP 502 for source '{source_id}': {url}"
            )
        destination.write_bytes(b"fake zip bytes")

    monkeypatch.setattr(acquirer, "_download_zip_once", fake_download_once)

    acquirer._download_zip(
        "https://api.worldbank.org/v2/en/country/all/indicator/X?source=2&downloadformat=csv",
        destination,
        source_id="wb_test",
    )

    assert calls["count"] == 3
    assert destination.read_bytes() == b"fake zip bytes"


def test_download_zip_raises_retryable_after_max_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    destination = tmp_path / "source.zip"

    acquirer = WorldBankIndicatorSnapshotAcquirer(
        plan=WorldBankAcquisitionPlan(
            max_download_attempts=2,
            retry_backoff_seconds=0,
        )
    )

    def fake_download_once(url: str, destination: Path, *, source_id: str) -> None:
        calls["count"] += 1
        raise RetryableWorldBankAcquisitionError(
            f"World Bank returned retryable HTTP 502 for source '{source_id}': {url}"
        )

    monkeypatch.setattr(acquirer, "_download_zip_once", fake_download_once)

    with pytest.raises(
        RetryableWorldBankAcquisitionError,
        match="after 2 download attempts",
    ):
        acquirer._download_zip(
            "https://api.worldbank.org/v2/en/country/all/indicator/X?source=2&downloadformat=csv",
            destination,
            source_id="wb_test",
        )

    assert calls["count"] == 2


def test_resolve_manifest_raw_root_uses_project_root_for_relative_paths() -> None:
    from country_compare.paths import PROJECT_ROOT
    from country_compare.pipelines.acquisition.snapshot import (
        _resolve_manifest_raw_root,
    )

    assert _resolve_manifest_raw_root("data/raw") == PROJECT_ROOT / "data/raw"


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
name: test_world_bank
raw_root: data/raw
processing:
  publish: false
defaults:
  adapter_id: world_bank_indicator_csv
  source_name: World Bank
  source_url: https://data.worldbank.org/
  read_options:
    skiprows: 4
sources:
  - source_id: wb_gdp_current_usd
    path: gdp_current_usd/wb_gdp_current_usd.csv
    metric_id: gdp_current_usd
    metric_name: GDP Current USD
    expected_indicator_code: NY.GDP.MKTP.CD
    unit: USD
    category: economy
    higher_is_better: true
""".strip() + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _world_bank_zip_payload(indicator_code: str) -> bytes:
    return _zip_payload(
        {
            "API_NY.GDP.MKTP.CD_DS2_en_csv_v2_1.csv": (
                '"Data Source","World Development Indicators"\n'
                "\n"
                '"Last Updated Date","2026-06-01"\n'
                "\n"
                '"Country Name","Country Code","Indicator Name","Indicator Code","1960"\n'
                f'"Israel","ISR","GDP (current US$)","{indicator_code}","123"\n'
            ),
            "Metadata_Country_API_NY.GDP.MKTP.CD_DS2_en_csv_v2_1.csv": (
                "Country Code,Region\n" "ISR,Middle East & North Africa\n"
            ),
            "Metadata_Indicator_API_NY.GDP.MKTP.CD_DS2_en_csv_v2_1.csv": (
                "INDICATOR_CODE,INDICATOR_NAME\n" "NY.GDP.MKTP.CD,GDP\n"
            ),
        }
    )


def _zip_payload(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        for name, content in files.items():
            zip_file.writestr(name, content)
    return buffer.getvalue()
