"""Application factory. The GUI, the CLI and external clients all talk to this API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from numericos import __version__
from numericos.api.errors import ERROR_RESPONSES, install_error_handlers
from numericos.api.middleware import CorrelationIdMiddleware
from numericos.api.routes import health
from numericos.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="NumericOS API",
        version=__version__,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Actor", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)  # outermost: every response carries the ID
    install_error_handlers(app)
    app.include_router(health.router, prefix="/v1", responses=ERROR_RESPONSES)
    return app


def create_app_from_env() -> FastAPI:
    """Factory for ``uvicorn --factory`` (used by ``numericos serve --reload``)."""
    return create_app(Settings())
