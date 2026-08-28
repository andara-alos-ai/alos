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
