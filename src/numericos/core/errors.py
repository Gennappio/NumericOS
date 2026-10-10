"""Typed errors with stable machine-readable codes; the API layer maps them to HTTP statuses."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    status_code = 404


class StaleRevisionError(DomainError):
    """The caller's ``version`` is not the current one (optimistic locking)."""

    code = "STALE_REVISION"
    status_code = 409


class ProjectMismatchError(DomainError):
    """The resource exists but does not belong to the project the caller named."""

    code = "PROJECT_MISMATCH"
    status_code = 409
