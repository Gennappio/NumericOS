"""Pure ASGI middleware that assigns one correlation ID per request.

A valid client-supplied ``X-Correlation-ID`` is kept, otherwise a ``cor_<ULID>`` is generated.
The ID is exposed as ``request.state.correlation_id`` and echoed on the response.
"""

from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from numericos.core.ids import new_id

HEADER = b"x-correlation-id"
VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = next(
            (value.decode("latin-1") for key, value in scope["headers"] if key == HEADER), None
        )
        correlation_id = (
            supplied if supplied and VALID_CORRELATION_ID.match(supplied) else new_id("cor")
        )
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(key == HEADER for key, _ in headers):
                    headers.append((HEADER, correlation_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)
