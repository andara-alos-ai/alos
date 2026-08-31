import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from alos.integrations.webhooks import N8nWebhookClient
from alos.platform.dispatch import OutboxDestination, OutboxEvent, OutboxStatus


class _Response:
    status = 202

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return b'{"accepted":true}'


def test_n8n_webhook_uses_canonical_payload_hmac_and_idempotency(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("alos.integrations.webhooks.client._open_no_redirect", fake_urlopen)
    event = OutboxEvent(
        outbox_event_id=uuid4(),
        organization_id=uuid4(),
        topic="reminder.delivery",
        aggregate_type="reminder",
        aggregate_id=uuid4(),
        destination=OutboxDestination.N8N_WEBHOOK,
        payload={"reminder_type": "OVERDUE", "escalation_level": 1},
        status=OutboxStatus.PROCESSING,
        attempt_count=1,
        max_attempts=5,
        available_at=datetime.now(UTC),
        locked_at=datetime.now(UTC),
        locked_by="unit-test",
        last_error=None,
        response_status=None,
        delivered_at=None,
        correlation_id=uuid4(),
        idempotency_key=f"reminder:{uuid4()}",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    secret = "n8n-signing-secret-at-least-32-characters"
    response = N8nWebhookClient(
        "https://n8n.example.test/webhook/alos",
        secret,
        7.5,
    ).send(event)

    request = captured["request"]
    body = request.data
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert response.status_code == 202
    assert captured["timeout"] == 7.5
    assert request.get_header("X-alos-signature") == f"sha256={expected}"
    assert request.get_header("X-alos-idempotency-key") == event.idempotency_key
    assert request.get_header("User-agent") == "ALOS-Worker/1.0"
    envelope = json.loads(body)
    assert envelope["event_id"] == str(event.outbox_event_id)
    assert envelope["data"]["reminder_type"] == "OVERDUE"
