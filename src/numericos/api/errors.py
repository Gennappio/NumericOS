"""One JSON error envelope for every non-2xx response of the public API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from numericos.core.errors import DomainError
from numericos.core.schemas import ErrorEnvelope

log = logging.getLogger("numericos.api")

#: Codes for errors raised by the framework itself (routing, validation); domain errors carry
#: their own code (see ``numericos.core.errors``).
HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}

#: Attach to routers so the envelope appears in the OpenAPI document.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorEnvelope, "description": "Resource not found"},
    422: {"model": ErrorEnvelope, "description": "Request validation failed"},
}

#: For mutations guarded by optimistic locking or a project assertion.
CONFLICT_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorEnvelope, "description": "Stale version or project mismatch"},
}


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": correlation_id,
        }
    }
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else None
    return JSONResponse(body, status_code=status_code, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        return error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code
        return error_response(request, status_code=exc.status_code, code=code, message=message)

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled error (correlation_id=%s)", getattr(request.state, "correlation_id", None)
        )
        return error_response(
            request, status_code=500, code="INTERNAL_ERROR", message="Internal server error"
        )
