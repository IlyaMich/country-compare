from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from country_compare.data.ingestion.base import SourceAdapter


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    adapter_id: str
    factory: Callable[[], SourceAdapter]
    description: str | None = None
