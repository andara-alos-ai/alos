from fastapi.testclient import TestClient

from alos.main import app

client = TestClient(app)


def test_health_reports_llm_disabled_by_default() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["llm_provider"] == "disabled"


def test_agents_endpoint_returns_18_agents() -> None:
    response = client.get("/api/v1/agents")

    assert response.status_code == 200
    assert len(response.json()) == 18


def test_operational_endpoint_requires_authentication() -> None:
    response = client.get("/api/v1/work-items")

    assert response.status_code == 401


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
