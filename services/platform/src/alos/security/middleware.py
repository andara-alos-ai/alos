"""HTTP security headers, origin controls, rate limits, and safe request metrics."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from alos.config import Settings
from alos.security.tokens import SESSION_COOKIE_NAME

logger = logging.getLogger("alos.http")


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._errors = 0
        self._latency_seconds = 0.0

    def observe(self, method: str, path: str, status_code: int, latency: float) -> None:
        with self._lock:
            self._requests[(method, _normalized_metric_path(path), status_code)] += 1
            if status_code >= 500:
                self._errors += 1
            self._latency_seconds += latency

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# TYPE alos_api_requests_total counter",
                *(
                    "alos_api_requests_total"
                    f'{{method="{method}",path="{path}",status="{code}"}} {count}'
                    for (method, path, code), count in sorted(self._requests.items())
                ),
                "# TYPE alos_api_errors_total counter",
                f"alos_api_errors_total {self._errors}",
                "# TYPE alos_api_latency_seconds_total counter",
                f"alos_api_latency_seconds_total {self._latency_seconds:.6f}",
            ]
        return "\n".join(lines) + "\n"


metrics = RequestMetrics()


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings
        self._rate_lock = threading.Lock()
        self._requests_by_client: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.monotonic()
        correlation_id = _correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = correlation_id
        rejection = self._reject(request, correlation_id)
        if rejection is not None:
            return rejection
        try:
            response = await call_next(request)
        except Exception:
            latency = time.monotonic() - started
            metrics.observe(request.method, request.url.path, 500, latency)
            logger.exception(
                json.dumps(
                    {
                        "event": "api_request_failed",
                        "method": request.method,
                        "path": request.url.path,
                        "correlation_id": str(correlation_id),
                        "latency_ms": round(latency * 1000, 2),
                    }
                )
            )
            # FastAPI's default unhandled-error response is plain text and does
            # not retain the request correlation ID.  Keep implementation
            # details server-side while returning an actionable, traceable
            # response to the UI and to support staff.
            return _error(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                (
                    "Layanan ALOS mengalami kegagalan internal. "
                    "Hubungi administrator dengan referensi ini."
                ),
                correlation_id,
            )
        latency = time.monotonic() - started
        response_status = response.status_code
        # A third-party/legacy response object must never bring down a valid
        # request merely because it omitted the optional status field.
        if not isinstance(response_status, int):
            response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        metrics.observe(request.method, request.url.path, response_status, latency)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if self._settings.environment in {"staging", "production"}:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        logger.info(
            json.dumps(
                {
                    "event": "api_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response_status,
                    "correlation_id": str(correlation_id),
                    "latency_ms": round(latency * 1000, 2),
                }
            )
        )
        return response

    def _reject(self, request: Request, correlation_id: UUID) -> Response | None:
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                too_large = int(content_length) > self._settings.api_max_request_bytes
            except ValueError:
                too_large = True
            if too_large:
                return _error(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "request body exceeds server policy",
                    correlation_id,
                )
        if not self._allow_rate(request):
            return _error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "request rate limit exceeded",
                correlation_id,
            )
        if (
            self._settings.environment in {"staging", "production"}
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and SESSION_COOKIE_NAME in request.cookies
            and not request.headers.get("Authorization", "").startswith("Bearer ")
            and request.headers.get("Origin") != self._settings.web_origin.rstrip("/")
        ):
            return _error(
                status.HTTP_403_FORBIDDEN,
                "cookie-authenticated mutation requires the configured Origin",
                correlation_id,
            )
        return None

    def _allow_rate(self, request: Request) -> bool:
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{request.url.path}"
        with self._rate_lock:
            history = self._requests_by_client[key]
            while history and history[0] < now - 60:
                history.popleft()
            if len(history) >= self._settings.api_rate_limit_per_minute:
                return False
            history.append(now)
        return True


def install_security_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(SecurityMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin.rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )


def _correlation_id(value: str | None) -> UUID:
    if value:
        try:
            return UUID(value)
        except ValueError:
            pass
    return uuid4()


_UUID_PATH_SEGMENT = re.compile(
    r"(?<=/)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)",
    re.IGNORECASE,
)
_NUMERIC_PATH_SEGMENT = re.compile(r"(?<=/)\d{4,}(?=/|$)")


def _normalized_metric_path(path: str) -> str:
    """Keep Prometheus label cardinality bounded for entity routes."""

    return _NUMERIC_PATH_SEGMENT.sub(":id", _UUID_PATH_SEGMENT.sub(":id", path))


def _error(status_code: int, detail: str, correlation_id: UUID) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail, "correlation_id": str(correlation_id)},
    )
    response.headers["X-Correlation-ID"] = str(correlation_id)
    return response
