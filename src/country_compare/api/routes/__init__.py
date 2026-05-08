from __future__ import annotations

from fastapi import FastAPI

from country_compare.api.routes import comparison, health, metadata, prediction


def include_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(
        metadata.router,
        prefix="/api/v1/metadata",
        tags=["metadata"],
    )
    app.include_router(
        comparison.router,
        prefix="/api/v1",
        tags=["comparison"],
    )
    app.include_router(
        prediction.router,
        prefix="/api/v1/prediction",
        tags=["prediction"],
    )
