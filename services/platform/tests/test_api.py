from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from alos.config import Settings, get_settings
from alos.entrypoints import api as api_entrypoint
from alos.main import app
from alos.platform.identity import PilotProfile
from alos.security import Role

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_client_cookies() -> None:
    client.cookies.clear()


def test_health_reports_llm_disabled_by_default() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["service"] == "ALOS"
    assert response.json()["llm_provider"] == "disabled"


def test_oidc_is_disabled_safely_by_default() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        oidc_provider="disabled",
    )
    try:
        isolated_client = TestClient(app)
        status_response = isolated_client.get("/api/v1/auth/oidc/status")
        login_response = isolated_client.get("/api/v1/auth/oidc/login")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert status_response.status_code == 200
    assert status_response.json() == {"enabled": False, "provider": None}
    assert login_response.status_code == 404


def test_pilot_login_uses_persisted_assignments_not_browser_claims(monkeypatch) -> None:
    profile = PilotProfile(
        user_id=uuid4(),
        organization_id=uuid4(),
        email="finance.a.pilot@example.test",
        display_name="Keuangan Penguji A",
        roles=frozenset({Role.FINANCE}),
        division_codes=frozenset({"FINANCE"}),
        project_ids=frozenset({uuid4()}),
    )

    class FakePilotProfileStore:
        def __init__(self, _engine) -> None:
            pass

        def list_profiles(self) -> tuple[PilotProfile, ...]:
            return (profile,)

        def get_profile(self, user_id: UUID) -> PilotProfile:
            if user_id != profile.user_id:
                raise KeyError("Profil pilot tidak ditemukan atau tidak aktif")
            return profile

    monkeypatch.setattr(api_entrypoint, "PilotProfileStore", FakePilotProfileStore)

    profile_response = client.get("/api/v1/auth/pilot-profiles")
    token_response = client.post(
        "/api/v1/auth/pilot-login",
        json={"user_id": str(profile.user_id)},
    )
    principal_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert profile_response.status_code == 200
    assert profile_response.json()[0]["email"] == profile.email
    assert token_response.status_code == 200
    assert principal_response.status_code == 200
    assert principal_response.json()["roles"] == ["FINANCE"]
    assert principal_response.json()["division_codes"] == ["FINANCE"]


def test_pilot_authentication_endpoints_are_hidden_outside_local_environment() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        environment="staging",
        auth_signing_secret="a-production-only-signing-secret-with-32-bytes",
    )
    try:
        isolated_client = TestClient(app)
        context = isolated_client.get("/api/v1/auth/pilot-bootstrap-context")
        profiles = isolated_client.get("/api/v1/auth/pilot-profiles")
        login = isolated_client.post(
            "/api/v1/auth/pilot-login",
            json={"user_id": str(uuid4())},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert context.status_code == 404
    assert profiles.status_code == 404
    assert login.status_code == 404


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
    assert {agent["agent_kind"] for agent in response.json()} == {"CORE"}
    assert {agent["contract_version"] for agent in response.json()} == {"1.0.0"}
    assert all(agent["parent_agent_id"] is None for agent in response.json())

    exact_response = client.get(
        "/api/v1/agents/BCA",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        params={"version": "0.1.0"},
    )
    assert exact_response.status_code == 200
    assert exact_response.json()["agent_id"] == "BCA"
    assert exact_response.json()["version"] == "0.1.0"


def test_registry_and_runtime_diagnostic_require_authentication() -> None:
    assert client.get("/api/v1/agents").status_code == 401
    assert client.get("/api/v1/workflows").status_code == 401
    assert client.get("/api/v1/genesis/source-packs").status_code == 401
    assert client.get("/api/v1/genesis/configuration-registers").status_code == 401
    assert client.post("/api/v1/agent-runs/prepare", json={}).status_code == 401


def test_authenticated_user_can_read_source_pack_status_without_document_content() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["AUDITOR"],
        },
    )
    response = client.get(
        "/api/v1/genesis/source-packs",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    packs = {item["pack_id"]: item for item in response.json()}
    assert packs["ALOS-SP-MASTER-AN-DRAFT"]["status"] == "DRAFT"
    assert packs["ALOS-SP-MASTER-AN-DRAFT"]["contains_unratified_values"] is True
    assert "STAGE" in packs["ALOS-SP-MASTER-AN-DRAFT"]["blocked_uses"]


def test_operational_user_cannot_read_restricted_source_pack_metadata() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["SALES"],
            "division_codes": ["SALES_MARKETING"],
        },
    )
    response = client.get(
        "/api/v1/genesis/source-packs",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 403


def test_auditor_can_read_canonical_configuration_without_production_effect() -> None:
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["AUDITOR"],
        },
    )
    response = client.get(
        "/api/v1/genesis/configuration-registers",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    register = response.json()[0]
    assert register["register_id"] == "ALOS-CR-MASTER-AN"
    assert register["production_effect"] is False
    assert len(register["mappings"]) == 16


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


def test_runtime_diagnostic_returns_versioned_contract_snapshot() -> None:
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
        "/api/v1/agent-runs/prepare",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        json={
            "agent_id": "BCA",
            "agent_version": "0.1.0",
            "capability": "check_budget_deterministically",
            "input_references": ["payment-request:runtime-contract-test"],
            "requested_tools": ["deterministic.calculator"],
            "correlation_id": str(uuid4()),
            "idempotency_key": "runtime-contract-snapshot",
        },
    )

    assert response.status_code == 201
    assert response.json()["contract_version"] == "1.0.0"
    assert response.json()["agent_kind"] == "CORE"
    assert len(response.json()["contract_digest"]) == 64
    assert response.json()["contract_snapshot"]["agent_id"] == "BCA"


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
    assert "/api/v1/system/pilot-readiness" in paths
    assert "/api/v1/system/go-live-readiness" in paths
    assert "/api/v1/uat/runs" in paths
    assert "/api/v1/uat/runs/{uat_run_id}/scenarios/{scenario_id}" in paths
    assert "/api/v1/uat/runs/{uat_run_id}/signoffs" in paths
    assert "/api/v1/projects/{project_id}/status" in paths
    assert "/api/v1/system/outbox/{outbox_event_id}/requeue" in paths


def test_phase_four_operational_endpoint_requires_authentication() -> None:
    assert client.get("/api/v1/operational/work-queue").status_code == 401
    assert client.get("/api/v1/system/operations-health").status_code == 401
    assert (
        client.get(
            "/api/v1/system/pilot-readiness", params={"project_id": str(uuid4())}
        ).status_code
        == 401
    )
    assert (
        client.get("/api/v1/uat/runs", params={"project_id": str(uuid4())}).status_code
        == 401
    )
    assert (
        client.patch(
            f"/api/v1/projects/{uuid4()}/status",
            json={"status": "ACTIVE", "reason": "Authentication required."},
        ).status_code
        == 401
    )


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
