import hashlib
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.main import app
from alos.persistence.migrations import psycopg_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_payment_request_is_approved_paid_and_reconciled() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_token = _token(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created: dict[str, Any] = {}

    try:
        requester = _create_finance_user(client, admin_headers, "requester")
        approver = _create_finance_user(client, admin_headers, "approver")
        created["user_ids"] = [requester, approver]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"FIN-{uuid4().hex[:8].upper()}", "name": "Finance Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        requester_token = _token(
            client, organization_id, requester, ["FINANCE"], ["FINANCE"], [project_id]
        )
        approver_token = _token(
            client, organization_id, approver, ["FINANCE"], ["FINANCE"], [project_id]
        )
        requester_headers = {"Authorization": f"Bearer {requester_token}"}
        approver_headers = {"Authorization": f"Bearer {approver_token}"}
        budget_response = client.post(
            "/api/v1/finance/budgets",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "code": "OPERASIONAL",
                "name": "Anggaran Operasional Sintetis",
                "allocated_amount": "1000000.00",
            },
        )
        assert budget_response.status_code == 201
        budget_id = budget_response.json()["budget_id"]
        created["budget_id"] = budget_id
        content = f"synthetic-invoice-{uuid4()}".encode()
        document_response = client.post(
            "/api/v1/documents",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "logical_name": "Invoice Sintetis",
                "classification": "INTERNAL",
                "object_key": f"synthetic/{uuid4()}.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "media_type": "application/pdf",
                "size_bytes": len(content),
            },
        )
        assert document_response.status_code == 201
        document = document_response.json()
        created.update(document)
        request_response = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"pay-{uuid4().hex}"},
            json={
                "project_id": project_id,
                "budget_id": budget_id,
                "document_version_id": document["document_version_id"],
                "payee_name": "Vendor Sintetis",
                "purpose": "Pembelian material pengujian",
                "amount": "100000.00",
                "requested_payment_date": date.today().isoformat(),
            },
        )
        assert request_response.status_code == 201, request_response.text
        payment = request_response.json()
        created.update(payment)
        assert payment["current_step"] == "finance-approval"
        assert payment["budget_available"] is True
        self_decision_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers=requester_headers,
            json={"decision": "APPROVED", "reason": "Percobaan approval oleh requester."},
        )
        assert self_decision_response.status_code == 403
        assert "sendiri" in self_decision_response.json()["detail"]
        decision_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers=approver_headers,
            json={"decision": "APPROVED", "reason": "Bukti dan anggaran sesuai."},
        )
        assert decision_response.status_code == 200, decision_response.text
        assert decision_response.json()["current_step"] == "payment-action"
        reference = f"TRX-{uuid4().hex[:12].upper()}"
        invalid_amount_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers=approver_headers,
            json={
                "payment_reference": f"INVALID-{reference}",
                "amount": "99999.00",
                "paid_at": datetime.now(UTC).isoformat(),
                "evidence_document_version_id": document["document_version_id"],
            },
        )
        assert invalid_amount_response.status_code == 409
        assert "berbeda" in invalid_amount_response.json()["detail"]
        paid_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers=approver_headers,
            json={
                "payment_reference": reference,
                "amount": "100000.00",
                "paid_at": datetime.now(UTC).isoformat(),
                "evidence_document_version_id": document["document_version_id"],
            },
        )
        assert paid_response.status_code == 200, paid_response.text
        assert paid_response.json()["current_step"] == "reconciliation"
        reconcile_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/reconciliation",
            headers={**approver_headers, "Idempotency-Key": f"recon-{uuid4().hex}"},
            json={
                "transaction_reference": reference,
                "transaction_amount": "100000.00",
                "currency": "IDR",
            },
        )
        assert reconcile_response.status_code == 200, reconcile_response.text
        result = reconcile_response.json()
        assert result["current_step"] == "reconciled"
        assert result["reconciliation_status"] == "MATCHED"
        assert result["terminal"] is True
        budgets_query = client.get(
            "/api/v1/finance/budgets",
            headers=requester_headers,
            params={"project_id": project_id, "status": "ACTIVE"},
        )
        assert budgets_query.status_code == 200, budgets_query.text
        assert budgets_query.json()["items"][0]["available_amount"] == "900000.00"
        payment_query = client.get(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}",
            headers=requester_headers,
        )
        assert payment_query.status_code == 200, payment_query.text
        assert payment_query.json()["status"] == "RECONCILED"
        approval_query = client.get(
            "/api/v1/approvals",
            headers=requester_headers,
            params={"project_id": project_id, "status": "APPROVED"},
        )
        assert approval_query.status_code == 200, approval_query.text
        assert approval_query.json()["total"] == 1
        with psycopg.connect(database_url) as connection:
            amounts = connection.execute(
                "SELECT committed_amount, spent_amount FROM finance.budgets WHERE budget_id = %s",
                (budget_id,),
            ).fetchone()
            assert amounts == (Decimal("0.00"), Decimal("100000.00"))
    finally:
        _cleanup(database_url, created)


def _create_finance_user(client: TestClient, headers: dict[str, str], label: str) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"finance-{label}-{uuid4().hex[:8]}@example.test",
            "display_name": f"Finance {label.title()} Sintetis",
            "division_code": "FINANCE",
            "role": "FINANCE",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def _token(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
    projects: list[object] | None = None,
) -> str:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": roles,
            "division_codes": divisions,
            "project_ids": [str(item) for item in projects or []],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _cleanup(database_url: str, created: dict[str, Any]) -> None:
    with psycopg.connect(database_url) as connection:
        payment_id = created.get("payment_request_id")
        workflow_id = created.get("workflow_run_id")
        work_item_id = created.get("work_item_id")
        approval_id = created.get("approval_request_id")
        if payment_id:
            connection.execute(
                "DELETE FROM finance.reconciliations WHERE payment_request_id = %s", (payment_id,)
            )
            connection.execute(
                "DELETE FROM finance.payment_records WHERE payment_request_id = %s", (payment_id,)
            )
            connection.execute(
                "DELETE FROM finance.payment_requests WHERE payment_request_id = %s", (payment_id,)
            )
        if approval_id:
            connection.execute(
                "DELETE FROM governance.approval_decisions WHERE approval_request_id = %s",
                (approval_id,),
            )
            connection.execute(
                "DELETE FROM governance.approval_requests WHERE approval_request_id = %s",
                (approval_id,),
            )
        if workflow_id:
            for table in ("workflow.transition_events", "agents.agent_runs"):
                connection.execute(
                    f"DELETE FROM {table} WHERE workflow_run_id = %s", (workflow_id,)
                )  # noqa: S608
            connection.execute(
                "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s", (workflow_id,)
            )
        if work_item_id:
            connection.execute(
                "DELETE FROM platform.evidence WHERE work_item_id = %s", (work_item_id,)
            )
            connection.execute(
                "DELETE FROM governance.exceptions WHERE work_item_id = %s", (work_item_id,)
            )
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s", (work_item_id,)
            )
        if created.get("document_version_id"):
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_version_id = %s",
                (created["document_version_id"],),
            )
        if created.get("document_id"):
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s", (created["document_id"],)
            )
        if created.get("budget_id"):
            connection.execute(
                "DELETE FROM finance.budgets WHERE budget_id = %s", (created["budget_id"],)
            )
        entity_ids = [str(value) for key, value in created.items() if key.endswith("_id") and value]
        if entity_ids:
            connection.execute("DELETE FROM audit.entries WHERE entity_id = ANY(%s)", (entity_ids,))
        if created.get("project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
            )
        for user_id in created.get("user_ids", []):
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))
