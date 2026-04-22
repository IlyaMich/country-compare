from __future__ import annotations

import pandas as pd

from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import (
    clear_source_adapters,
    has_source_adapter,
    register_source_adapter,
    resolve_source_adapter,
)


class DummyAdapter(SourceAdapter):
    def to_standardized_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({"ok": [True]})


def test_register_and_resolve_source_adapter() -> None:
    clear_source_adapters(keep_builtins=True)
    register_source_adapter("dummy_adapter", DummyAdapter, replace=True)

    assert has_source_adapter("dummy_adapter") is True

    adapter = resolve_source_adapter("dummy_adapter")
    assert isinstance(adapter, DummyAdapter)
    assert bool(adapter.to_standardized_dataframe().iloc[0]["ok"]) is True
