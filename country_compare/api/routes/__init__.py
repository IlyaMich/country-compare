from __future__ import annotations

from fastapi import FastAPI

from country_compare.api.routes import health, metadata


def include_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(
        metadata.router,
        prefix="/api/v1/metadata",
        tags=["metadata"],
    )
