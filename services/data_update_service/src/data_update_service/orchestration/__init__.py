from __future__ import annotations

from typing import TYPE_CHECKING, Any

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult

if TYPE_CHECKING:
    from data_update_service.orchestration.runner import RunnerDependencies


__all__ = [
    "RefreshCommand",
    "RefreshResult",
    "RunnerDependencies",
    "run_refresh_job",
]


def __getattr__(name: str) -> Any:
    if name in {"RunnerDependencies", "run_refresh_job"}:
        from data_update_service.orchestration.runner import (
            RunnerDependencies,
            run_refresh_job,
        )

        return {
            "RunnerDependencies": RunnerDependencies,
            "run_refresh_job": run_refresh_job,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
