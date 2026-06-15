from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult

JobStatus = Literal[
    "accepted",
    "running",
    "source_acquired",
    "pipeline_completed",
    "validation_passed",
    "artifact_published",
    "completed",
    "completed_no_changes",
    "dry_run_completed",
    "failed_retryable",
    "failed_non_retryable",
]

TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        "completed",
        "completed_no_changes",
        "dry_run_completed",
        "failed_retryable",
        "failed_non_retryable",
    }
)


class DuplicateCommandConflictError(ValueError):
    """Raised when a reused command/idempotency key points at different job metadata."""


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    command_id: str
    idempotency_key: str
    source_family: str
    manifest_path: str
    mode: str
    acquisition_mode: str
    status: JobStatus
    dry_run: bool
    publish: bool
    promote: bool
    promotion_channel: str | None
    requested_by: str
    requested_at: datetime
    attempt: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_dataset_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: RefreshResult | None = None
    status_history: tuple[JobStatus, ...] = field(default_factory=lambda: ("accepted",))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES


class JobStore(Protocol):
    def create_or_get_job(self, command: RefreshCommand) -> JobRecord:
        """Create a job or return an existing idempotent job."""

    def get_job(self, job_id: str) -> JobRecord | None:
        """Return a job by id if present."""

    def mark_running(self, job_id: str) -> JobRecord:
        """Mark the job as running."""

    def update_status(self, job_id: str, status: JobStatus) -> JobRecord:
        """Record an intermediate job status."""

    def complete_job(self, result: RefreshResult) -> JobRecord:
        """Persist a terminal refresh result."""

    def result_for_job(self, job_id: str) -> RefreshResult | None:
        """Return the persisted result for a terminal job."""


class InMemoryJobStore:
    """Thread-safe in-memory job store for local tests and first orchestration wiring."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs_by_id: dict[str, JobRecord] = {}
        self._job_id_by_command_id: dict[str, str] = {}
        self._job_id_by_idempotency_key: dict[str, str] = {}

    def create_or_get_job(self, command: RefreshCommand) -> JobRecord:
        with self._lock:
            existing = self._find_existing(command)
            if existing is not None:
                self._validate_existing_job(command, existing)
                return deepcopy(existing)

            now = datetime.now(tz=UTC)
            record = JobRecord(
                job_id=command.job_id,
                command_id=command.command_id,
                idempotency_key=command.idempotency_key,
                source_family=command.source_family,
                manifest_path=command.manifest_path,
                mode=command.mode,
                acquisition_mode=command.acquisition_mode,
                status="accepted",
                dry_run=command.dry_run,
                publish=command.publish,
                promote=command.promote,
                promotion_channel=command.promotion_channel,
                requested_by=command.requested_by,
                requested_at=command.requested_at,
                attempt=command.attempt,
                max_attempts=command.max_attempts,
                created_at=now,
                updated_at=now,
            )
            self._jobs_by_id[command.job_id] = record
            self._job_id_by_command_id[command.command_id] = command.job_id
            self._job_id_by_idempotency_key[command.idempotency_key] = command.job_id
            return deepcopy(record)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs_by_id.get(job_id)
            return deepcopy(record) if record is not None else None

    def mark_running(self, job_id: str) -> JobRecord:
        with self._lock:
            now = datetime.now(tz=UTC)
            record = self._require_job(job_id)
            started_at = record.started_at or now
            updated = replace(
                record,
                status="running",
                started_at=started_at,
                updated_at=now,
                status_history=_append_status(record.status_history, "running"),
            )
            self._jobs_by_id[job_id] = updated
            return deepcopy(updated)

    def update_status(self, job_id: str, status: JobStatus) -> JobRecord:
        with self._lock:
            now = datetime.now(tz=UTC)
            record = self._require_job(job_id)
            updated = replace(
                record,
                status=status,
                updated_at=now,
                status_history=_append_status(record.status_history, status),
            )
            self._jobs_by_id[job_id] = updated
            return deepcopy(updated)

    def complete_job(self, result: RefreshResult) -> JobRecord:
        with self._lock:
            now = datetime.now(tz=UTC)
            record = self._require_job(result.job_id)
            status = _result_status_to_job_status(result.status)
            updated = replace(
                record,
                status=status,
                finished_at=now,
                updated_at=now,
                output_dataset_version=result.dataset_version,
                error_code=result.error_code,
                error_message=result.error_message,
                result=result,
                status_history=_append_status(record.status_history, status),
            )
            self._jobs_by_id[result.job_id] = updated
            return deepcopy(updated)

    def result_for_job(self, job_id: str) -> RefreshResult | None:
        with self._lock:
            record = self._jobs_by_id.get(job_id)
            if record is None or record.result is None:
                return None
            return record.result.model_copy(deep=True)

    def _find_existing(self, command: RefreshCommand) -> JobRecord | None:
        job_ids = {
            command.job_id if command.job_id in self._jobs_by_id else None,
            self._job_id_by_command_id.get(command.command_id),
            self._job_id_by_idempotency_key.get(command.idempotency_key),
        }
        existing_ids = {job_id for job_id in job_ids if job_id is not None}
        if not existing_ids:
            return None
        if len(existing_ids) > 1:
            raise DuplicateCommandConflictError(
                "command_id, job_id, and idempotency_key resolve to different jobs"
            )
        existing_job_id = next(iter(existing_ids))
        return self._jobs_by_id[existing_job_id]

    def _validate_existing_job(
        self, command: RefreshCommand, existing: JobRecord
    ) -> None:
        mismatches = []
        for field_name in (
            "job_id",
            "command_id",
            "idempotency_key",
            "source_family",
            "manifest_path",
            "mode",
            "acquisition_mode",
            "dry_run",
            "publish",
            "promote",
            "promotion_channel",
        ):
            if getattr(command, field_name) != getattr(existing, field_name):
                mismatches.append(field_name)
        if mismatches:
            joined = ", ".join(mismatches)
            raise DuplicateCommandConflictError(
                f"duplicate command has conflicting fields: {joined}"
            )

    def _require_job(self, job_id: str) -> JobRecord:
        record = self._jobs_by_id.get(job_id)
        if record is None:
            raise KeyError(f"unknown data refresh job: {job_id}")
        return record


def _append_status(
    history: tuple[JobStatus, ...], status: JobStatus
) -> tuple[JobStatus, ...]:
    if history and history[-1] == status:
        return history
    return (*history, status)


def _result_status_to_job_status(status: str) -> JobStatus:
    if status == "completed":
        return "completed"
    if status == "completed_no_changes":
        return "completed_no_changes"
    if status == "dry_run_completed":
        return "dry_run_completed"
    if status == "failed_retryable":
        return "failed_retryable"
    return "failed_non_retryable"
