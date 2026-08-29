from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject request bodies that exceed a deterministic byte limit."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self._max_bytes:
            await self._reject(send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._reject(send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps(
            {"detail": "Ukuran request melebihi batas layanan"},
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
