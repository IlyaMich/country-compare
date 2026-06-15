from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from data_update_service.orchestration.commands import RefreshCommand


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: str
    job_id: str
    command_id: str
    attempt_number: int
    started_at: datetime
    status: str
    finished_at: datetime | None = None
    worker_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class AttemptStore(Protocol):
    def start_attempt(
        self,
        command: RefreshCommand,
        *,
        worker_id: str | None = None,
    ) -> AttemptRecord:
        """Record the start of one refresh attempt."""

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AttemptRecord:
        """Record the terminal result of one refresh attempt."""

    def list_attempts(self, job_id: str) -> list[AttemptRecord]:
        """Return attempts for a job ordered by attempt number."""


class InMemoryAttemptStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._attempts_by_id: dict[str, AttemptRecord] = {}

    def start_attempt(
        self,
        command: RefreshCommand,
        *,
        worker_id: str | None = None,
    ) -> AttemptRecord:
        with self._lock:
            attempt_id = _attempt_id(command.job_id, command.attempt)
            existing = self._attempts_by_id.get(attempt_id)
            if existing is not None:
                updated = replace(
                    existing,
                    status="running",
                    worker_id=worker_id,
                    finished_at=None,
                    error_code=None,
                    error_message=None,
                )
                self._attempts_by_id[attempt_id] = updated
                return deepcopy(updated)

            record = AttemptRecord(
                attempt_id=attempt_id,
                job_id=command.job_id,
                command_id=command.command_id,
                attempt_number=command.attempt,
                started_at=datetime.now(tz=UTC),
                status="running",
                worker_id=worker_id,
            )
            self._attempts_by_id[attempt_id] = record
            return deepcopy(record)

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AttemptRecord:
        with self._lock:
            existing = self._attempts_by_id.get(attempt_id)
            if existing is None:
                raise KeyError(f"unknown refresh attempt: {attempt_id}")

            updated = replace(
                existing,
                status=status,
                finished_at=datetime.now(tz=UTC),
                error_code=error_code,
                error_message=error_message,
            )
            self._attempts_by_id[attempt_id] = updated
            return deepcopy(updated)

    def list_attempts(self, job_id: str) -> list[AttemptRecord]:
        with self._lock:
            attempts = [
                attempt
                for attempt in self._attempts_by_id.values()
                if attempt.job_id == job_id
            ]
            return deepcopy(
                sorted(attempts, key=lambda attempt: attempt.attempt_number)
            )


def _attempt_id(job_id: str, attempt_number: int) -> str:
    return f"{job_id}_attempt_{attempt_number}"
