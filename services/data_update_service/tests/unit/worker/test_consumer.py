from __future__ import annotations

import pytest

from data_update_service.infrastructure.job_store import InMemoryJobStore
from data_update_service.infrastructure.locks import InMemorySourceLockManager
from data_update_service.settings import DataUpdateSettings
from data_update_service.worker.consumer import build_worker_dependencies


def test_build_worker_dependencies_uses_memory_backend_by_default() -> None:
    settings = DataUpdateSettings(job_store="memory")

    dependencies = build_worker_dependencies(settings)

    assert isinstance(dependencies.job_store, InMemoryJobStore)
    assert isinstance(dependencies.source_locks, InMemorySourceLockManager)


def test_build_worker_dependencies_requires_database_url_for_postgres() -> None:
    settings = DataUpdateSettings(job_store="postgres", database_url=None)

    with pytest.raises(ValueError, match="DATA_UPDATE_DATABASE_URL"):
        build_worker_dependencies(settings)
