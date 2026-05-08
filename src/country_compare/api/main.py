from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from country_compare import __version__
from country_compare.api.errors import register_exception_handlers
from country_compare.api.routes import include_routers
from country_compare.api.security import enforce_optional_api_key
from country_compare.api.settings import ApiSettings


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    resolved_settings = settings or ApiSettings.from_env()
    docs_url = "/docs" if resolved_settings.enable_docs else None
    redoc_url = "/redoc" if resolved_settings.enable_docs else None
    openapi_url = "/openapi.json" if resolved_settings.enable_docs else None

    app = FastAPI(
        title="Country Compare API",
        version=__version__,
        description=(
            "Read-only HTTP API for country metadata, comparisons, scoring, "
            "and prediction workflows. API behavior is configured through "
            "COUNTRY_COMPARE_API_* environment variables."
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.api_settings = resolved_settings

    app.middleware("http")(enforce_optional_api_key)

    if resolved_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    include_routers(app)

    return app


app = create_app()
