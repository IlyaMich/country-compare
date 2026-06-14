from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol


class SourceLockUnavailableError(RuntimeError):
    """Raised when another job already holds a source-family lock."""


@dataclass(frozen=True, slots=True)
class SourceLock:
    source_family: str
    locked_by_job_id: str
    locked_at: datetime
    expires_at: datetime


class SourceLockManager(Protocol):
    def acquire(
        self,
        source_family: str,
        job_id: str,
    ) -> AbstractContextManager[SourceLock]:
        """Acquire a lock for the given source family and job ID, blocking if necessary."""


class NoopSourceLockManager:
    """Lock manager used when callers intentionally do not need source serialization."""

    @contextmanager
    def acquire(self, source_family: str, job_id: str) -> Iterator[SourceLock]:
        now = datetime.now(tz=UTC)
        yield SourceLock(
            source_family=source_family,
            locked_by_job_id=job_id,
            locked_at=now,
            expires_at=now,
        )


class InMemorySourceLockManager:
    """Thread-safe source lock manager for tests and local orchestration."""

    def __init__(self, *, ttl_seconds: int = 7200) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._guard = RLock()
        self._locks: dict[str, SourceLock] = {}

    @contextmanager
    def acquire(self, source_family: str, job_id: str) -> Iterator[SourceLock]:
        lock = self._acquire_lock(source_family, job_id)
        try:
            yield lock
        finally:
            self.release(source_family, job_id)

    def current_lock(self, source_family: str) -> SourceLock | None:
        with self._guard:
            lock = self._locks.get(source_family)
            if lock is None or self._is_expired(lock):
                self._locks.pop(source_family, None)
                return None
            return lock

    def release(self, source_family: str, job_id: str) -> None:
        with self._guard:
            lock = self._locks.get(source_family)
            if lock is not None and lock.locked_by_job_id == job_id:
                self._locks.pop(source_family, None)

    def _acquire_lock(self, source_family: str, job_id: str) -> SourceLock:
        with self._guard:
            existing = self._locks.get(source_family)
            if existing is not None and not self._is_expired(existing):
                if existing.locked_by_job_id != job_id:
                    raise SourceLockUnavailableError(
                        f"source_family {source_family!r} is already locked by job "
                        f"{existing.locked_by_job_id!r}"
                    )
                return existing

            now = datetime.now(tz=UTC)
            lock = SourceLock(
                source_family=source_family,
                locked_by_job_id=job_id,
                locked_at=now,
                expires_at=now + self._ttl,
            )
            self._locks[source_family] = lock
            return lock

    @staticmethod
    def _is_expired(lock: SourceLock) -> bool:
        return lock.expires_at <= datetime.now(tz=UTC)
