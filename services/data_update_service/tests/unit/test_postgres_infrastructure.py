from __future__ import annotations

import pytest

from data_update_service.infrastructure.postgres import (
    PostgresInfrastructureError,
    PostgresJobStore,
    PostgresSourceLockManager,
)


def test_postgres_job_store_rejects_empty_database_url() -> None:
    with pytest.raises(ValueError, match="database_url must not be empty"):
        PostgresJobStore("")


def test_postgres_source_lock_manager_rejects_empty_database_url() -> None:
    with pytest.raises(ValueError, match="database_url must not be empty"):
        PostgresSourceLockManager("")


def test_postgres_source_lock_manager_rejects_invalid_ttl() -> None:
    with pytest.raises(ValueError, match="ttl_seconds must be greater than zero"):
        PostgresSourceLockManager("postgresql://example/db", ttl_seconds=0)


def test_postgres_job_store_reports_missing_optional_dependency() -> None:
    store = PostgresJobStore("postgresql://example/db")

    try:
        import psycopg  # noqa: F401
    except ModuleNotFoundError:
        with pytest.raises(PostgresInfrastructureError, match="postgres"):
            store.initialize_schema()
