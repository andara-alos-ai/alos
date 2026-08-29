from uuid import uuid4

from fastapi.testclient import TestClient

from alos.main import app

client = TestClient(app)


def test_health_reports_llm_disabled_by_default() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["llm_provider"] == "disabled"


def test_agents_endpoint_returns_18_agents() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["IT_ADMIN"],
        },
    )
    response = client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 18


def test_registry_and_runtime_diagnostic_require_authentication() -> None:
    assert client.get("/api/v1/agents").status_code == 401
    assert client.get("/api/v1/workflows").status_code == 401
    assert client.post("/api/v1/agent-runs/prepare", json={}).status_code == 401


def test_runtime_diagnostic_rejects_business_user() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["SALES"],
            "division_codes": ["SALES_MARKETING"],
        },
    )
    response = client.post(
        "/api/v1/agent-runs/prepare",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        json={
            "agent_id": "SLA",
            "capability": "validate_lead_fields",
            "input_references": ["lead:test"],
            "requested_tools": ["alos.lead.read"],
            "material_action": False,
            "correlation_id": str(uuid4()),
            "idempotency_key": "runtime-security-test",
        },
    )

    assert response.status_code == 403


def test_it_admin_cannot_operate_sales_business_workflow() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
        },
    )
    response = client.post(
        "/api/v1/leads",
        headers={
            "Authorization": f"Bearer {token_response.json()['access_token']}",
            "Idempotency-Key": "it-business-boundary-test",
        },
        json={
            "project_id": str(uuid4()),
            "full_name": "Lead Batas IT",
            "phone": "081234567890",
            "source": "security-test",
            "consent_recorded": True,
        },
    )

    assert response.status_code == 403


def test_auditor_cannot_create_exception() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["AUDITOR"],
        },
    )
    response = client.post(
        "/api/v1/exceptions",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        json={"category": "SECURITY_TEST", "severity": "LOW"},
    )

    assert response.status_code == 403


def test_operational_endpoint_requires_authentication() -> None:
    response = client.get("/api/v1/work-items")

    assert response.status_code == 401


def test_phase_four_operational_contract_is_published() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/operational/work-queue" in paths
    assert "/api/v1/operational/work-items/{work_item_id}/claim" in paths
    assert "/api/v1/operational/deadlines/evaluate" in paths
    assert "/api/v1/approvals/{approval_request_id}/claim" in paths
    assert "/api/v1/exceptions/{exception_id}/transition" in paths
    assert "/api/v1/capas/{capa_id}/transition" in paths
    assert "/api/v1/system/operations-health" in paths
    assert "/api/v1/system/outbox/{outbox_event_id}/requeue" in paths


def test_phase_four_operational_endpoint_requires_authentication() -> None:
    assert client.get("/api/v1/operational/work-queue").status_code == 401
    assert client.get("/api/v1/system/operations-health").status_code == 401


def test_local_environment_can_issue_signed_development_token() -> None:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": "00000000-0000-0000-0000-000000000001",
            "organization_id": "00000000-0000-0000-0000-000000000002",
            "roles": ["IT_ADMIN"],
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"].startswith("alos1.")


def test_authenticated_principal_returns_verified_token_context() -> None:
    user_id, organization_id = uuid4(), uuid4()
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": ["SALES"],
            "division_codes": ["SALES_MARKETING"],
        },
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id)
    assert response.json()["organization_id"] == str(organization_id)
    assert response.json()["roles"] == ["SALES"]
