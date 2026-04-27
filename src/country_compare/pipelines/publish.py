from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.access import save_metric_dataframe, save_metric_dataset
from country_compare.pipelines.errors import PublicationError
from country_compare.pipelines.models import PublicationReport


def publish_dataframe(
    dataframe: pd.DataFrame,
    *,
    store: Any | None = None,
    write_metric_dataset: bool = False,
) -> PublicationReport:
    target_backend = None
    target_path = None
    if store is not None:
        target_backend = getattr(store, "backend_name", None) or getattr(
            store, "backend", None
        )
        path_value = getattr(store, "path", None)
        target_path = str(path_value) if path_value is not None else None

    report = PublicationReport(
        attempted=True,
        ok=False,
        row_count=int(len(dataframe.index)),
        target_backend=str(target_backend) if target_backend is not None else None,
        target_path=target_path,
        wrote_metric_dataset=write_metric_dataset,
    )

    try:
        if write_metric_dataset:
            from country_compare.data.validation import dataframe_to_metric_dataset

            dataset = dataframe_to_metric_dataset(dataframe)
            save_metric_dataset(dataset, store=store)
        else:
            save_metric_dataframe(dataframe, store=store)
    except Exception as exc:  # pragma: no cover - simple wrapper
        report.error = str(exc)
        raise PublicationError(str(exc)) from exc

    report.ok = True
    return report
