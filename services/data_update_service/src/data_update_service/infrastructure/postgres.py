from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from data_update_service.infrastructure.attempt_store import AttemptRecord
from data_update_service.infrastructure.dataset_registry import (
    DatasetChannelRecord,
    DatasetVersionRecord,
    build_dataset_channel_record,
    build_dataset_version_record,
)
from data_update_service.infrastructure.job_store import (
    DuplicateCommandConflictError,
    JobRecord,
    JobStatus,
)
from data_update_service.infrastructure.locks import (
    SourceLock,
    SourceLockUnavailableError,
)
from data_update_service.orchestration.artifact_package import ArtifactPackage
from data_update_service.orchestration.commands import PromotionChannel, RefreshCommand
from data_update_service.orchestration.results import RefreshResult


class PostgresInfrastructureError(RuntimeError):
    """Raised when Postgres infrastructure is not configured or unavailable."""


class PostgresJobStore:
    """Postgres-backed implementation of the JobStore protocol."""

    def __init__(self, database_url: str, *, initialize_schema: bool = False) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        self.database_url = database_url
        if initialize_schema:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_CREATE_DATA_REFRESH_JOBS_SQL)
                cursor.execute("""
                    ALTER TABLE data_refresh_jobs
                    ADD COLUMN IF NOT EXISTS acquisition_mode TEXT NOT NULL DEFAULT 'local'
                    """)
                cursor.execute(_CREATE_DATA_REFRESH_ATTEMPTS_SQL)

    def create_or_get_job(self, command: RefreshCommand) -> JobRecord:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                existing = _find_existing_job(cursor, command)
                if existing is not None:
                    _validate_existing_job(command, existing)
                    return self._advance_existing_attempt_if_needed(command, existing)

                now = datetime.now(tz=UTC)
                cursor.execute(
                    """
                    INSERT INTO data_refresh_jobs (
                        job_id,
                        command_id,
                        idempotency_key,
                        source_family,
                        manifest_path,
                        mode,
                        acquisition_mode,
                        status,
                        dry_run,
                        publish,
                        promote,
                        promotion_channel,
                        requested_by,
                        requested_at,
                        attempt,
                        max_attempts,
                        created_at,
                        updated_at,
                        status_history
                    )
                    VALUES (
                        %(job_id)s,
                        %(command_id)s,
                        %(idempotency_key)s,
                        %(source_family)s,
                        %(manifest_path)s,
                        %(mode)s,
                        %(acquisition_mode)s,
                        'accepted',
                        %(dry_run)s,
                        %(publish)s,
                        %(promote)s,
                        %(promotion_channel)s,
                        %(requested_by)s,
                        %(requested_at)s,
                        %(attempt)s,
                        %(max_attempts)s,
                        %(created_at)s,
                        %(updated_at)s,
                        %(status_history)s::jsonb
                    )
                    RETURNING *
                    """,
                    {
                        "job_id": command.job_id,
                        "command_id": command.command_id,
                        "idempotency_key": command.idempotency_key,
                        "source_family": command.source_family,
                        "manifest_path": command.manifest_path,
                        "mode": command.mode,
                        "acquisition_mode": command.acquisition_mode,
                        "dry_run": command.dry_run,
                        "publish": command.publish,
                        "promote": command.promote,
                        "promotion_channel": command.promotion_channel,
                        "requested_by": command.requested_by,
                        "requested_at": command.requested_at,
                        "attempt": command.attempt,
                        "max_attempts": command.max_attempts,
                        "created_at": now,
                        "updated_at": now,
                        "status_history": json.dumps(["accepted"]),
                    },
                )
                row = cursor.fetchone()
                if row is None:
                    raise PostgresInfrastructureError(
                        "failed to insert data refresh job"
                    )
                return _row_to_job_record(row)

    def get_job(self, job_id: str) -> JobRecord | None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM data_refresh_jobs WHERE job_id = %s",
                    (job_id,),
                )
                row = cursor.fetchone()
                return _row_to_job_record(row) if row is not None else None

    def mark_running(self, job_id: str) -> JobRecord:
        now = datetime.now(tz=UTC)
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                record = _require_job(cursor, job_id)
                started_at = record.started_at or now
                history = _append_status(record.status_history, "running")
                cursor.execute(
                    """
                    UPDATE data_refresh_jobs
                    SET status = 'running',
                        started_at = %(started_at)s,
                        updated_at = %(updated_at)s,
                        status_history = %(status_history)s::jsonb
                    WHERE job_id = %(job_id)s
                    RETURNING *
                    """,
                    {
                        "job_id": job_id,
                        "started_at": started_at,
                        "updated_at": now,
                        "status_history": json.dumps(list(history)),
                    },
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(f"unknown data refresh job: {job_id}")
                return _row_to_job_record(row)

    def update_status(self, job_id: str, status: JobStatus) -> JobRecord:
        now = datetime.now(tz=UTC)
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                record = _require_job(cursor, job_id)
                history = _append_status(record.status_history, status)
                cursor.execute(
                    """
                    UPDATE data_refresh_jobs
                    SET status = %(status)s,
                        updated_at = %(updated_at)s,
                        status_history = %(status_history)s::jsonb
                    WHERE job_id = %(job_id)s
                    RETURNING *
                    """,
                    {
                        "job_id": job_id,
                        "status": status,
                        "updated_at": now,
                        "status_history": json.dumps(list(history)),
                    },
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(f"unknown data refresh job: {job_id}")
                return _row_to_job_record(row)

    def complete_job(self, result: RefreshResult) -> JobRecord:
        now = datetime.now(tz=UTC)
        status = _result_status_to_job_status(result.status)
        result_payload = result.model_dump(mode="json")

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                record = _require_job(cursor, result.job_id)
                history = _append_status(record.status_history, status)
                cursor.execute(
                    """
                    UPDATE data_refresh_jobs
                    SET status = %(status)s,
                        finished_at = %(finished_at)s,
                        updated_at = %(updated_at)s,
                        output_dataset_version = %(output_dataset_version)s,
                        error_code = %(error_code)s,
                        error_message = %(error_message)s,
                        result_payload = %(result_payload)s::jsonb,
                        status_history = %(status_history)s::jsonb
                    WHERE job_id = %(job_id)s
                    RETURNING *
                    """,
                    {
                        "job_id": result.job_id,
                        "status": status,
                        "finished_at": now,
                        "updated_at": now,
                        "output_dataset_version": result.dataset_version,
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                        "result_payload": json.dumps(result_payload),
                        "status_history": json.dumps(list(history)),
                    },
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(f"unknown data refresh job: {result.job_id}")
                return _row_to_job_record(row)

    def result_for_job(self, job_id: str) -> RefreshResult | None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT result_payload FROM data_refresh_jobs WHERE job_id = %s",
                    (job_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                payload = row.get("result_payload")
                if payload is None:
                    return None
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return RefreshResult.model_validate(payload)

    def _advance_existing_attempt_if_needed(
        self,
        command: RefreshCommand,
        existing: JobRecord,
    ) -> JobRecord:
        if existing.is_terminal or command.attempt <= existing.attempt:
            return existing

        updated_at = datetime.now(tz=UTC)

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE data_refresh_jobs
                    SET attempt = %(attempt)s,
                        max_attempts = %(max_attempts)s,
                        updated_at = %(updated_at)s
                    WHERE job_id = %(job_id)s
                    RETURNING *
                    """,
                    {
                        "job_id": existing.job_id,
                        "attempt": command.attempt,
                        "max_attempts": command.max_attempts,
                        "updated_at": updated_at,
                    },
                )
                row = cursor.fetchone()

        if row is None:
            raise KeyError(f"unknown data refresh job: {existing.job_id}")

        return _row_to_job_record(row)


class PostgresAttemptStore:
    """Postgres-backed refresh attempt store."""

    def __init__(self, database_url: str, *, initialize_schema: bool = False) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")

        self.database_url = database_url

        if initialize_schema:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_CREATE_DATA_REFRESH_JOBS_SQL)
                cursor.execute("""
                    ALTER TABLE data_refresh_jobs
                    ADD COLUMN IF NOT EXISTS acquisition_mode TEXT NOT NULL DEFAULT 'local'
                    """)
                cursor.execute(_CREATE_DATA_REFRESH_ATTEMPTS_SQL)

    def start_attempt(
        self,
        command: RefreshCommand,
        *,
        worker_id: str | None = None,
    ) -> AttemptRecord:
        now = datetime.now(tz=UTC)
        attempt_id = _attempt_id(command.job_id, command.attempt)

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO data_refresh_attempts (
                        attempt_id,
                        job_id,
                        command_id,
                        attempt_number,
                        started_at,
                        status,
                        worker_id
                    )
                    VALUES (
                        %(attempt_id)s,
                        %(job_id)s,
                        %(command_id)s,
                        %(attempt_number)s,
                        %(started_at)s,
                        'running',
                        %(worker_id)s
                    )
                    ON CONFLICT (job_id, attempt_number)
                    DO UPDATE SET
                        status = 'running',
                        worker_id = EXCLUDED.worker_id,
                        finished_at = NULL,
                        error_code = NULL,
                        error_message = NULL
                    RETURNING *
                    """,
                    {
                        "attempt_id": attempt_id,
                        "job_id": command.job_id,
                        "command_id": command.command_id,
                        "attempt_number": command.attempt,
                        "started_at": now,
                        "worker_id": worker_id,
                    },
                )
                row = cursor.fetchone()

        if row is None:
            raise PostgresInfrastructureError(
                f"failed to start refresh attempt: {attempt_id}"
            )

        return _row_to_attempt_record(row)

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AttemptRecord:
        now = datetime.now(tz=UTC)

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE data_refresh_attempts
                    SET status = %(status)s,
                        finished_at = %(finished_at)s,
                        error_code = %(error_code)s,
                        error_message = %(error_message)s
                    WHERE attempt_id = %(attempt_id)s
                    RETURNING *
                    """,
                    {
                        "attempt_id": attempt_id,
                        "status": status,
                        "finished_at": now,
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                )
                row = cursor.fetchone()

        if row is None:
            raise KeyError(f"unknown refresh attempt: {attempt_id}")

        return _row_to_attempt_record(row)

    def list_attempts(self, job_id: str) -> list[AttemptRecord]:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM data_refresh_attempts
                    WHERE job_id = %s
                    ORDER BY attempt_number ASC
                    """,
                    (job_id,),
                )
                rows = cursor.fetchall()

        return [_row_to_attempt_record(row) for row in rows]


class PostgresDatasetRegistry:
    """Postgres-backed implementation of the DatasetRegistry protocol."""

    def __init__(self, database_url: str, *, initialize_schema: bool = False) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        self.database_url = database_url
        if initialize_schema:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_CREATE_DATA_REFRESH_JOBS_SQL)
                cursor.execute("""
                    ALTER TABLE data_refresh_jobs
                    ADD COLUMN IF NOT EXISTS acquisition_mode TEXT NOT NULL DEFAULT 'local'
                    """)
                cursor.execute(_CREATE_DATASET_VERSIONS_SQL)
                cursor.execute(_CREATE_DATASET_CHANNELS_SQL)

    def register_dataset_version(
        self,
        *,
        command: RefreshCommand,
        artifact: ArtifactPackage,
        result: RefreshResult,
    ) -> DatasetVersionRecord:
        record = build_dataset_version_record(
            command=command,
            artifact=artifact,
            result=result,
        )

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dataset_versions (
                        dataset_version,
                        source_family,
                        artifact_uri,
                        parquet_sha256,
                        manifest_sha256,
                        catalog_sha256,
                        validation_report_uri,
                        diff_report_uri,
                        row_count,
                        country_count,
                        metric_count,
                        year_min,
                        year_max,
                        validation_status,
                        created_by_job_id,
                        created_at
                    )
                    VALUES (
                        %(dataset_version)s,
                        %(source_family)s,
                        %(artifact_uri)s,
                        %(parquet_sha256)s,
                        %(manifest_sha256)s,
                        %(catalog_sha256)s,
                        %(validation_report_uri)s,
                        %(diff_report_uri)s,
                        %(row_count)s,
                        %(country_count)s,
                        %(metric_count)s,
                        %(year_min)s,
                        %(year_max)s,
                        %(validation_status)s,
                        %(created_by_job_id)s,
                        %(created_at)s
                    )
                    ON CONFLICT (dataset_version) DO NOTHING
                    """,
                    record.as_dict(),
                )

                cursor.execute(
                    """
                    SELECT *
                    FROM dataset_versions
                    WHERE dataset_version = %s
                    """,
                    (record.dataset_version,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PostgresInfrastructureError(
                        f"failed to register dataset version: {record.dataset_version}"
                    )
                return _row_to_dataset_version_record(row)

    def get_dataset_version(self, dataset_version: str) -> DatasetVersionRecord | None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM dataset_versions
                    WHERE dataset_version = %s
                    """,
                    (dataset_version,),
                )
                row = cursor.fetchone()
                return _row_to_dataset_version_record(row) if row is not None else None

    def list_dataset_versions(
        self,
        *,
        source_family: str | None = None,
    ) -> list[DatasetVersionRecord]:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                if source_family is None:
                    cursor.execute("""
                        SELECT *
                        FROM dataset_versions
                        ORDER BY created_at ASC, dataset_version ASC
                        """)
                else:
                    cursor.execute(
                        """
                        SELECT *
                        FROM dataset_versions
                        WHERE source_family = %s
                        ORDER BY created_at ASC, dataset_version ASC
                        """,
                        (source_family,),
                    )
                return [
                    _row_to_dataset_version_record(row) for row in cursor.fetchall()
                ]

    def promote_dataset_version(
        self,
        *,
        dataset_version: str,
        channel: PromotionChannel,
        promoted_by: str,
    ) -> DatasetChannelRecord:
        version = self.get_dataset_version(dataset_version)
        if version is None:
            raise KeyError(f"unknown dataset version: {dataset_version}")

        channel_record = build_dataset_channel_record(
            version=version,
            channel=channel,
            promoted_by=promoted_by,
        )

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dataset_channels (
                        channel,
                        dataset_version,
                        promoted_by,
                        promoted_at
                    )
                    VALUES (
                        %(channel)s,
                        %(dataset_version)s,
                        %(promoted_by)s,
                        %(promoted_at)s
                    )
                    ON CONFLICT (channel)
                    DO UPDATE SET
                        dataset_version = EXCLUDED.dataset_version,
                        promoted_by = EXCLUDED.promoted_by,
                        promoted_at = EXCLUDED.promoted_at
                    """,
                    {
                        "channel": channel_record.channel,
                        "dataset_version": channel_record.dataset_version,
                        "promoted_by": channel_record.promoted_by,
                        "promoted_at": channel_record.promoted_at,
                    },
                )

        reloaded = self.get_channel(
            source_family=version.source_family,
            channel=channel,
        )
        if reloaded is None:
            raise PostgresInfrastructureError(
                f"failed to promote dataset version {dataset_version!r} to {channel!r}"
            )
        return reloaded

    def get_channel(
        self,
        *,
        source_family: str,
        channel: PromotionChannel,
    ) -> DatasetChannelRecord | None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.channel,
                        v.source_family,
                        c.dataset_version,
                        v.artifact_uri,
                        v.parquet_sha256,
                        c.promoted_by,
                        c.promoted_at
                    FROM dataset_channels c
                    JOIN dataset_versions v
                      ON v.dataset_version = c.dataset_version
                    WHERE c.channel = %s
                      AND v.source_family = %s
                    """,
                    (channel, source_family),
                )
                row = cursor.fetchone()
                return _row_to_dataset_channel_record(row) if row is not None else None

    def list_channels(
        self,
        *,
        source_family: str | None = None,
    ) -> list[DatasetChannelRecord]:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                if source_family is None:
                    cursor.execute("""
                        SELECT
                            c.channel,
                            v.source_family,
                            c.dataset_version,
                            v.artifact_uri,
                            v.parquet_sha256,
                            c.promoted_by,
                            c.promoted_at
                        FROM dataset_channels c
                        JOIN dataset_versions v
                          ON v.dataset_version = c.dataset_version
                        ORDER BY v.source_family ASC, c.channel ASC
                        """)
                else:
                    cursor.execute(
                        """
                        SELECT
                            c.channel,
                            v.source_family,
                            c.dataset_version,
                            v.artifact_uri,
                            v.parquet_sha256,
                            c.promoted_by,
                            c.promoted_at
                        FROM dataset_channels c
                        JOIN dataset_versions v
                          ON v.dataset_version = c.dataset_version
                        WHERE v.source_family = %s
                        ORDER BY v.source_family ASC, c.channel ASC
                        """,
                        (source_family,),
                    )

                return [
                    _row_to_dataset_channel_record(row) for row in cursor.fetchall()
                ]


class PostgresSourceLockManager:
    """Postgres-backed source-family lock manager."""

    def __init__(
        self,
        database_url: str,
        *,
        ttl_seconds: int = 7200,
        initialize_schema: bool = False,
    ) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self.database_url = database_url
        self.ttl = timedelta(seconds=ttl_seconds)
        if initialize_schema:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_CREATE_SOURCE_LOCKS_SQL)

    @contextmanager
    def acquire(self, source_family: str, job_id: str) -> Iterator[SourceLock]:
        lock = self._acquire_lock(source_family, job_id)
        try:
            yield lock
        finally:
            self.release(source_family, job_id)

    def current_lock(self, source_family: str) -> SourceLock | None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM source_locks
                    WHERE source_family = %s
                      AND expires_at <= now()
                    """,
                    (source_family,),
                )
                cursor.execute(
                    "SELECT * FROM source_locks WHERE source_family = %s",
                    (source_family,),
                )
                row = cursor.fetchone()
                return _row_to_source_lock(row) if row is not None else None

    def release(self, source_family: str, job_id: str) -> None:
        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM source_locks
                    WHERE source_family = %s
                      AND locked_by_job_id = %s
                    """,
                    (source_family, job_id),
                )

    def _acquire_lock(self, source_family: str, job_id: str) -> SourceLock:
        now = datetime.now(tz=UTC)
        expires_at = now + self.ttl

        with _connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM source_locks
                    WHERE source_family = %s
                      AND expires_at <= now()
                    """,
                    (source_family,),
                )
                cursor.execute(
                    """
                    INSERT INTO source_locks (
                        source_family,
                        locked_by_job_id,
                        locked_at,
                        expires_at
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source_family) DO NOTHING
                    RETURNING *
                    """,
                    (source_family, job_id, now, expires_at),
                )
                inserted = cursor.fetchone()
                if inserted is not None:
                    return _row_to_source_lock(inserted)

                cursor.execute(
                    "SELECT * FROM source_locks WHERE source_family = %s",
                    (source_family,),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise SourceLockUnavailableError(
                        f"source_family {source_family!r} lock was not acquired"
                    )

                lock = _row_to_source_lock(existing)
                if lock.locked_by_job_id == job_id:
                    cursor.execute(
                        """
                        UPDATE source_locks
                        SET expires_at = %s
                        WHERE source_family = %s
                          AND locked_by_job_id = %s
                        RETURNING *
                        """,
                        (expires_at, source_family, job_id),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise SourceLockUnavailableError(
                            f"source_family {source_family!r} lock was not refreshed"
                        )
                    return _row_to_source_lock(row)

                raise SourceLockUnavailableError(
                    f"source_family {source_family!r} is already locked by job "
                    f"{lock.locked_by_job_id!r}"
                )


def _connect(database_url: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise PostgresInfrastructureError(
            "Postgres support requires installing the 'postgres' extra: "
            'python -m pip install -e "services/data_update_service[postgres]"'
        ) from exc

    return psycopg.connect(database_url, row_factory=dict_row)


def _find_existing_job(cursor: Any, command: RefreshCommand) -> JobRecord | None:
    cursor.execute(
        """
        SELECT *
        FROM data_refresh_jobs
        WHERE job_id = %(job_id)s
           OR command_id = %(command_id)s
           OR idempotency_key = %(idempotency_key)s
        """,
        {
            "job_id": command.job_id,
            "command_id": command.command_id,
            "idempotency_key": command.idempotency_key,
        },
    )
    rows = cursor.fetchall()
    if not rows:
        return None

    records = [_row_to_job_record(row) for row in rows]
    job_ids = {record.job_id for record in records}
    if len(job_ids) > 1:
        raise DuplicateCommandConflictError(
            "command_id, job_id, and idempotency_key resolve to different jobs"
        )

    return records[0]


def _require_job(cursor: Any, job_id: str) -> JobRecord:
    cursor.execute(
        "SELECT * FROM data_refresh_jobs WHERE job_id = %s",
        (job_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise KeyError(f"unknown data refresh job: {job_id}")
    return _row_to_job_record(row)


def _validate_existing_job(command: RefreshCommand, existing: JobRecord) -> None:
    mismatches: list[str] = []
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


def _row_to_job_record(row: dict[str, Any]) -> JobRecord:
    status = cast(JobStatus, row["status"])
    status_history = _coerce_status_history(row.get("status_history"))
    result_payload = row.get("result_payload")
    result = _coerce_refresh_result(result_payload)

    return JobRecord(
        job_id=str(row["job_id"]),
        command_id=str(row["command_id"]),
        idempotency_key=str(row["idempotency_key"]),
        source_family=str(row["source_family"]),
        manifest_path=str(row["manifest_path"]),
        mode=str(row["mode"]),
        acquisition_mode=str(row.get("acquisition_mode") or "local"),
        status=status,
        dry_run=bool(row["dry_run"]),
        publish=bool(row["publish"]),
        promote=bool(row["promote"]),
        promotion_channel=(
            str(row["promotion_channel"]) if row.get("promotion_channel") else None
        ),
        requested_by=str(row["requested_by"]),
        requested_at=_ensure_aware_datetime(row["requested_at"]),
        attempt=int(row["attempt"]),
        max_attempts=int(row["max_attempts"]),
        created_at=_ensure_aware_datetime(row["created_at"]),
        updated_at=_ensure_aware_datetime(row["updated_at"]),
        started_at=_optional_datetime(row.get("started_at")),
        finished_at=_optional_datetime(row.get("finished_at")),
        output_dataset_version=(
            str(row["output_dataset_version"])
            if row.get("output_dataset_version")
            else None
        ),
        error_code=str(row["error_code"]) if row.get("error_code") else None,
        error_message=(str(row["error_message"]) if row.get("error_message") else None),
        result=result,
        status_history=status_history,
    )


def _row_to_source_lock(row: dict[str, Any]) -> SourceLock:
    return SourceLock(
        source_family=str(row["source_family"]),
        locked_by_job_id=str(row["locked_by_job_id"]),
        locked_at=_ensure_aware_datetime(row["locked_at"]),
        expires_at=_ensure_aware_datetime(row["expires_at"]),
    )


def _coerce_status_history(value: Any) -> tuple[JobStatus, ...]:
    if value is None:
        return ("accepted",)

    raw_values: list[Any]
    if isinstance(value, str):
        raw_values = list(json.loads(value))
    elif isinstance(value, list):
        raw_values = value
    elif isinstance(value, tuple):
        raw_values = list(value)
    else:
        raw_values = ["accepted"]

    if not raw_values:
        return ("accepted",)

    return tuple(cast(JobStatus, str(item)) for item in raw_values)


def _coerce_refresh_result(value: Any) -> RefreshResult | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return RefreshResult.model_validate(value)


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _ensure_aware_datetime(value)


def _ensure_aware_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _append_status(
    history: tuple[JobStatus, ...],
    status: JobStatus,
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


def _row_to_attempt_record(row: dict[str, Any]) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=str(row["attempt_id"]),
        job_id=str(row["job_id"]),
        command_id=str(row["command_id"]),
        attempt_number=int(row["attempt_number"]),
        started_at=_ensure_aware_datetime(row["started_at"]),
        finished_at=_optional_datetime(row.get("finished_at")),
        status=str(row["status"]),
        worker_id=str(row["worker_id"]) if row.get("worker_id") else None,
        error_code=str(row["error_code"]) if row.get("error_code") else None,
        error_message=str(row["error_message"]) if row.get("error_message") else None,
    )


def _row_to_dataset_version_record(row: dict[str, Any]) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version=str(row["dataset_version"]),
        source_family=str(row["source_family"]),
        artifact_uri=str(row["artifact_uri"]),
        parquet_sha256=str(row["parquet_sha256"]),
        validation_report_uri=(
            str(row["validation_report_uri"])
            if row.get("validation_report_uri")
            else None
        ),
        diff_report_uri=(
            str(row["diff_report_uri"]) if row.get("diff_report_uri") else None
        ),
        row_count=int(row["row_count"]),
        country_count=int(row["country_count"]),
        metric_count=int(row["metric_count"]),
        year_min=int(row["year_min"]) if row.get("year_min") is not None else None,
        year_max=int(row["year_max"]) if row.get("year_max") is not None else None,
        validation_status=str(row["validation_status"]),
        created_by_job_id=str(row["created_by_job_id"]),
        created_at=_ensure_aware_datetime(row["created_at"]),
        manifest_sha256=str(row.get("manifest_sha256") or ""),
        catalog_sha256=str(row.get("catalog_sha256") or ""),
    )


def _row_to_dataset_channel_record(row: dict[str, Any]) -> DatasetChannelRecord:
    return DatasetChannelRecord(
        channel=cast(PromotionChannel, row["channel"]),
        source_family=str(row["source_family"]),
        dataset_version=str(row["dataset_version"]),
        artifact_uri=str(row["artifact_uri"]),
        parquet_sha256=str(row["parquet_sha256"]),
        promoted_by=str(row["promoted_by"]),
        promoted_at=_ensure_aware_datetime(row["promoted_at"]),
    )


def _attempt_id(job_id: str, attempt_number: int) -> str:
    return f"{job_id}_attempt_{attempt_number}"


_CREATE_DATA_REFRESH_JOBS_SQL = """
CREATE TABLE IF NOT EXISTS data_refresh_jobs (
    job_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    source_family TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    mode TEXT NOT NULL,
    acquisition_mode TEXT NOT NULL DEFAULT 'local',
    status TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    publish BOOLEAN NOT NULL DEFAULT TRUE,
    promote BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_channel TEXT,
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    output_dataset_version TEXT,
    error_code TEXT,
    error_message TEXT,
    result_payload JSONB,
    status_history JSONB NOT NULL DEFAULT '["accepted"]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_SOURCE_LOCKS_SQL = """
CREATE TABLE IF NOT EXISTS source_locks (
    source_family TEXT PRIMARY KEY,
    locked_by_job_id TEXT NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
)
"""

_CREATE_DATA_REFRESH_ATTEMPTS_SQL = """
CREATE TABLE IF NOT EXISTS data_refresh_attempts (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES data_refresh_jobs(job_id) ON DELETE CASCADE,
    command_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    worker_id TEXT,
    error_code TEXT,
    error_message TEXT,
    UNIQUE (job_id, attempt_number)
)
"""

_CREATE_DATASET_VERSIONS_SQL = """
CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_version TEXT PRIMARY KEY,
    source_family TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    parquet_sha256 TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL DEFAULT '',
    catalog_sha256 TEXT NOT NULL DEFAULT '',
    validation_report_uri TEXT,
    diff_report_uri TEXT,
    row_count INTEGER NOT NULL,
    country_count INTEGER NOT NULL,
    metric_count INTEGER NOT NULL,
    year_min INTEGER,
    year_max INTEGER,
    validation_status TEXT NOT NULL,
    created_by_job_id TEXT REFERENCES data_refresh_jobs(job_id),
    created_at TIMESTAMPTZ NOT NULL
)
"""

_CREATE_DATASET_CHANNELS_SQL = """
CREATE TABLE IF NOT EXISTS dataset_channels (
    channel TEXT PRIMARY KEY,
    dataset_version TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
    promoted_by TEXT NOT NULL,
    promoted_at TIMESTAMPTZ NOT NULL
)
"""
