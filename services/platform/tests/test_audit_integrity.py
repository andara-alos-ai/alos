from datetime import UTC, datetime
from uuid import UUID

from alos.audit import compute_audit_entry_hash


def test_audit_hash_is_deterministic_and_sensitive_to_payload() -> None:
    values = {
        "organization_id": UUID("00000000-0000-0000-0000-000000000001"),
        "actor_id": "00000000-0000-0000-0000-000000000002",
        "action": "test.created",
        "entity_type": "test",
        "entity_id": "00000000-0000-0000-0000-000000000003",
        "correlation_id": UUID("00000000-0000-0000-0000-000000000004"),
        "reason": "integrity-test",
        "before": None,
        "after": {"status": "CREATED"},
        "occurred_at": datetime(2026, 9, 1, tzinfo=UTC),
        "previous_hash": None,
    }

    first = compute_audit_entry_hash(**values)
    second = compute_audit_entry_hash(**values)
    changed = compute_audit_entry_hash(**{**values, "action": "test.changed"})

    assert first == second
    assert first != changed
    assert len(first) == 64
