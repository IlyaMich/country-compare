from __future__ import annotations

import pytest

from data_update_service.infrastructure.locks import (
    InMemorySourceLockManager,
    SourceLockUnavailableError,
)


def test_in_memory_source_lock_manager_serializes_by_source_family() -> None:
    locks = InMemorySourceLockManager()

    with locks.acquire("world_bank", "job-1"):
        with pytest.raises(SourceLockUnavailableError):
            with locks.acquire("world_bank", "job-2"):
                pass

    with locks.acquire("world_bank", "job-2") as lock:
        assert lock.locked_by_job_id == "job-2"


def test_in_memory_source_lock_manager_allows_different_sources() -> None:
    locks = InMemorySourceLockManager()

    with locks.acquire("world_bank", "job-1"):
        with locks.acquire("oecd", "job-2") as lock:
            assert lock.source_family == "oecd"
