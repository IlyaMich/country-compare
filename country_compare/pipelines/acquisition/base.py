from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from country_compare.pipelines.models import AcquiredAsset, SourceSpec


class RawAcquirer(ABC):
    @abstractmethod
    def acquire(self, source_spec: SourceSpec, *, raw_root: Path | None = None) -> list[AcquiredAsset]:
        raise NotImplementedError
