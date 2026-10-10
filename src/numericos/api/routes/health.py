from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from sqlalchemy.exc import OperationalError

from numericos import __version__
from numericos.core.schemas import HealthOut
from numericos.persistence import migrate

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness of the API process and state of its database")
def health(request: Request) -> HealthOut:
    settings = request.app.state.settings
    engine = request.app.state.engine
    expected = migrate.head_revision()
    db: Literal["ok", "unavailable"] = "ok"
    try:
        revision = migrate.current_revision(engine)
    except OperationalError:  # e.g. the data directory does not exist
        revision, db = None, "unavailable"
    status: Literal["ok", "degraded"] = "ok" if db == "ok" and revision == expected else "degraded"
    return HealthOut(
        status=status,
        app="numericos",
        version=__version__,
        time_utc=datetime.now(UTC),
        data_dir=str(settings.data_dir),
        db=db,
        schema_revision=revision,
        expected_revision=expected,
    )
