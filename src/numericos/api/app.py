"""Application factory. The GUI, the CLI and external clients all talk to this API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from numericos import __version__
from numericos.api.errors import ERROR_RESPONSES, install_error_handlers
from numericos.api.middleware import CorrelationIdMiddleware
from numericos.api.routes import cards, events, health, projects
from numericos.config import Settings
from numericos.events.notifier import EventNotifier
from numericos.persistence.engine import make_engine, make_session_factory


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


def _operation_id(route: APIRoute) -> str:
    """Stable, readable operation IDs (``create_project``) for generated clients."""
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Migrations are NOT applied here: ``numericos serve`` / ``db upgrade`` do."""
    settings = settings or Settings()
    app = FastAPI(
        title="NumericOS API",
        version=__version__,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
        lifespan=_lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.notifier = EventNotifier()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Actor", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)  # outermost: every response carries the ID
    install_error_handlers(app)
    for router in (health.router, projects.router, cards.router, events.router):
        app.include_router(router, prefix="/v1", responses=ERROR_RESPONSES)
    return app


def create_app_from_env() -> FastAPI:
    """Factory for ``uvicorn --factory`` (used by ``numericos serve --reload``)."""
    return create_app(Settings())
