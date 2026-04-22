from __future__ import annotations

from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import (
    AdapterRegistryError,
    clear_source_adapters,
    has_source_adapter,
    list_registered_source_adapters,
    register_source_adapter,
    resolve_source_adapter,
    unregister_source_adapter,
)

__all__ = [
    "AdapterRegistryError",
    "SourceAdapter",
    "clear_source_adapters",
    "has_source_adapter",
    "list_registered_source_adapters",
    "register_source_adapter",
    "resolve_source_adapter",
    "unregister_source_adapter",
]