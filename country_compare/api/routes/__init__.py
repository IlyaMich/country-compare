from __future__ import annotations

from fastapi import FastAPI

from country_compare.api.routes import health


def include_routers(app: FastAPI) -> None:
    """Register Phase 1 routers."""

    app.include_router(health.router)
