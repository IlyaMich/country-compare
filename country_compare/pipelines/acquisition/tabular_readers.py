from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.pipelines.errors import UnsupportedFormatError
from country_compare.pipelines.models import AcquiredAsset


def read_acquired_asset(
    asset: AcquiredAsset,
    *,
    read_options: dict[str, Any] | None = None,
) -> pd.DataFrame:
    options = dict(read_options or {})
    path = asset.local_path
    file_format = asset.file_format.lower()

    if file_format == "csv":
        return pd.read_csv(path, **options)
    if file_format == "parquet":
        return pd.read_parquet(path, **options)
    if file_format == "excel":
        return pd.read_excel(path, **options)

    raise UnsupportedFormatError(
        f"unsupported acquired asset format '{asset.file_format}' for path '{path}'"
    )
