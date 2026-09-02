from __future__ import annotations

import json
import threading
import time
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


class RateLimitMiddleware:
    """In-process fixed-window protection; production must also rate-limit at the edge."""

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int,
        auth_requests_per_minute: int,
    ) -> None:
        self._app = app
        self._general_limit = requests_per_minute
        self._auth_limit = auth_requests_per_minute
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str, int], int] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if path in {"/health", "/ready"}:
            await self._app(scope, receive, send)
            return
        client_value = scope.get("client")
        client = str(client_value[0]) if isinstance(client_value, tuple) else "unknown"
        group = "auth" if "/auth/" in path else "api"
        limit = self._auth_limit if group == "auth" else self._general_limit
        window = int(time.monotonic() // 60)
        key = (client, group, window)
        with self._lock:
            count = self._windows.get(key, 0) + 1
            self._windows[key] = count
            if len(self._windows) > 10_000:
                self._windows = {
                    stored_key: stored_count
                    for stored_key, stored_count in self._windows.items()
                    if stored_key[2] >= window - 1
                }
        if count > limit:
            await self._reject(send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps(
            {"detail": "Batas request sementara tercapai; coba kembali setelah satu menit"},
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"retry-after", b"60"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
