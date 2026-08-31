from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from alos.platform.dispatch.models import OutboxEvent


class WebhookDeliveryError(RuntimeError):
    """Raised when an external webhook cannot confirm delivery."""


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    status_code: int


class WebhookClient(Protocol):
    def send(self, event: OutboxEvent) -> WebhookResponse: ...


class N8nWebhookClient:
    """Minimal signed n8n client with bounded I/O and no redirect customization."""

    def __init__(self, url: str, secret: str, timeout_seconds: float) -> None:
        self._url = url
        self._secret = secret.encode("utf-8")
        self._timeout_seconds = timeout_seconds

    def send(self, event: OutboxEvent) -> WebhookResponse:
        envelope = {
            "event_id": str(event.outbox_event_id),
            "event_type": event.topic,
            "occurred_at": event.created_at.isoformat(),
            "organization_id": str(event.organization_id),
            "correlation_id": str(event.correlation_id),
            "idempotency_key": event.idempotency_key,
            "data": event.payload,
        }
        body = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        signature = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        request = Request(  # noqa: S310 -- URL is operator configuration validated by Settings.
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ALOS-Worker/1.0",
                "X-ALOS-Event-ID": str(event.outbox_event_id),
                "X-ALOS-Idempotency-Key": event.idempotency_key,
                "X-ALOS-Signature": f"sha256={signature}",
            },
        )
        try:
            with _open_no_redirect(request, self._timeout_seconds) as response:
                status_code = int(response.status)
                response.read(1024)
        except HTTPError as exc:
            raise WebhookDeliveryError(f"n8n returned HTTP {exc.code}") from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise WebhookDeliveryError(f"n8n delivery failed: {type(exc).__name__}") from exc
        if status_code < 200 or status_code >= 300:
            raise WebhookDeliveryError(f"n8n returned HTTP {status_code}")
        return WebhookResponse(status_code=status_code)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        _request: Request,
        _file_pointer: object,
        _code: int,
        _message: str,
        _headers: object,
        _new_url: str,
    ) -> None:
        return None


def _open_no_redirect(request: Request, timeout_seconds: float) -> Any:
    opener = build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout_seconds)  # noqa: S310
