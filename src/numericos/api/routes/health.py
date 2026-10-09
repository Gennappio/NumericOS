from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from numericos import __version__
from numericos.core.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness of the API process")
def health() -> HealthOut:
    return HealthOut(status="ok", app="numericos", version=__version__, time_utc=datetime.now(UTC))
