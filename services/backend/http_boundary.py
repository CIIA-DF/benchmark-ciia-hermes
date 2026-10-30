"""Bounded HTTP bodies and safe responses, without buffering SSE output."""

import logging

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from contracts.models import ToolError

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 1024 * 1024


class HTTPBoundary:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        private = "authorization" in headers or scope["path"] not in {
            "/health",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/openapi.json",
        }
        started = False

        async def safe_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                outgoing = MutableHeaders(scope=message)
                if private:
                    outgoing["Cache-Control"] = "no-store"
                if message["status"] == 401:
                    outgoing.setdefault("WWW-Authenticate", "Bearer")
                started = True
            await send(message)

        async def too_large() -> None:
            scope.setdefault("state", {})["tool_error_code"] = "payload_too_large"
            await JSONResponse(
                status_code=413,
                content=ToolError(
                    code="payload_too_large", message="Corpo excede o limite de 1 MiB."
                ).model_dump(mode="json"),
            )(scope, receive, safe_send)

        length = headers.get("content-length")
        if length is not None and length.isascii() and length.isdecimal():
            normalized = length.lstrip("0") or "0"
            maximum = str(MAX_BODY_BYTES)
            if len(normalized) > len(maximum) or (
                len(normalized) == len(maximum) and normalized > maximum
            ):
                await too_large()
                return
        # Count actual bytes even without Content-Length or with a false smaller value.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                await too_large()
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        try:
            await self.app(scope, replay, safe_send)
        except Exception:
            if started:
                # Headers already sent: the SSE producer handles its own stream errors.
                raise
            scope.setdefault("state", {})["tool_error_code"] = "internal_error"
            logger.error("http_internal_error")
            await JSONResponse(
                status_code=500,
                content=ToolError(code="internal_error", message="Falha interna.").model_dump(
                    mode="json"
                ),
            )(scope, replay, safe_send)
