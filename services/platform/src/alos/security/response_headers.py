from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class SecurityHeadersMiddleware:
    """Apply browser hardening and prevent operational API responses being cached."""

    _BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"cache-control", b"no-store"),
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
        (b"cross-origin-resource-policy", b"same-site"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"referrer-policy", b"no-referrer"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-permitted-cross-domain-policies", b"none"),
    )

    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        self._app = app
        self._headers = self._BASE_HEADERS
        if hsts_enabled:
            self._headers += (
                (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        async def hardened_send(message: Message) -> None:
            if message.get("type") != "http.response.start":
                await send(message)
                return
            headers = list(message.get("headers", []))
            existing = {name.lower() for name, _ in headers}
            headers.extend(header for header in self._headers if header[0] not in existing)
            await send({**message, "headers": headers})

        await self._app(scope, receive, hardened_send)
