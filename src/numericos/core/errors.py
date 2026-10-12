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


class InvalidRequestError(DomainError):
    """A request that is well formed but not valid for the operation it targets.

    ``details`` uses the same ``errors`` list as schema validation failures.
    """

    code = "VALIDATION_ERROR"
    status_code = 422


class ProtocolFrozenError(DomainError):
    """The protocol of an experiment that already has runs cannot change."""

    code = "PROTOCOL_FROZEN"
    status_code = 409


class IdempotencyConflictError(DomainError):
    """An idempotency key was reused with a different request."""

    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class NotReproducibleError(DomainError):
    """The run cannot be repeated automatically from what was recorded."""

    code = "NOT_REPRODUCIBLE"
    status_code = 409


class ArtifactMissingError(DomainError):
    """An artifact is registered but its file is no longer in the run directory."""

    code = "ARTIFACT_MISSING"
    status_code = 409


class ExecutionNotTrustedError(DomainError):
    """Commands may be executed only for a project whose directory was explicitly trusted."""

    code = "EXECUTION_NOT_TRUSTED"
    status_code = 409


class NotAGitRepositoryError(DomainError):
    """The project directory is not the top of a Git work tree."""

    code = "NOT_A_GIT_REPOSITORY"
    status_code = 409


class CursorAheadError(DomainError):
    """A stream cursor beyond the ledger head: the caller's cursor is from another ledger."""

    code = "CURSOR_AHEAD"
    status_code = 409
