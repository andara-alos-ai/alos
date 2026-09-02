import os

import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.main import app
from alos.observability import HealthStatus, evaluate_system_readiness

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_health_endpoint() -> None:
    client = TestClient(app)
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "llm_provider" in data


def test_readiness_endpoint_and_evaluator() -> None:
    settings = get_settings()
    report = evaluate_system_readiness(settings)
    assert report.application_name == settings.application_name
    assert report.status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED}
    assert report.all_passed is True

    # Validate components
    components = {c.component: c for c in report.checks}
    assert "database" in components
    assert components["database"].status == HealthStatus.HEALTHY

    assert "migrations" in components
    assert components["migrations"].status == HealthStatus.HEALTHY
    assert components["migrations"].details["applied_count"] >= 40

    assert "agent_registry" in components
    assert components["agent_registry"].status == HealthStatus.HEALTHY
    assert components["agent_registry"].details["core_agents"] == 18

    assert "audit_ledger" in components
    assert components["audit_ledger"].status == HealthStatus.HEALTHY

    assert "llm_gateway" in components
    assert components["llm_gateway"].status == HealthStatus.HEALTHY

    # Test HTTP endpoint
    client = TestClient(app)
    res = client.get("/api/v1/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in {"HEALTHY", "DEGRADED"}
    assert data["all_passed"] is True
    assert len(data["checks"]) >= 5
