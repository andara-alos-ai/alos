import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from alos import main
from alos.audit.reader import AuditReader
from alos.config import Settings
from alos.identity.authentication import IdentityAuthenticationRepository
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.security import tokens

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="staging",
        database_url=database_url,
        auth_signing_secret="a" * 32,
        llm_daily_request_limit=2,
        llm_daily_output_token_limit=2_400,
        llm_daily_cost_cap_usd=Decimal("0.25"),
        llm_max_output_tokens=1_200,
    )


def test_staging_password_session_and_governance_api(monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = psycopg_url(main.get_settings().database_url)
    database_name = f"alos_h6_auth_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        settings = _settings(temporary_url)
        repository = IdentityAuthenticationRepository(temporary_url)
        bootstrap = repository.bootstrap_director(
            email="andararejomakmur10@gmail.com",
            password="ALOS staging password with enough entropy",
            display_name="ALOS Director",
            workspace_key="ALOS_GOVERNANCE",
            workspace_name="ALOS Governance",
            settings=settings,
        )
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_identity_authentication_repository", lambda: repository)
        monkeypatch.setattr(main, "get_audit_reader", lambda: AuditReader(temporary_url))
        monkeypatch.setattr(tokens, "get_settings", lambda: settings)
        client = TestClient(main.app)

        denied = client.post(
            "/api/v1/auth/login",
            json={"email": "andararejomakmur10@gmail.com", "password": "wrong password"},
        )
        assert denied.status_code == 401
        assert denied.json() == {"detail": "invalid email or password"}

        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "andararejomakmur10@gmail.com",
                "password": "ALOS staging password with enough entropy",
            },
        )
        assert login.status_code == 200
        assert "access_token" not in login.json()
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "Secure" in login.headers["set-cookie"]
        assert login.headers["cache-control"] == "no-store"
        assert login.json()["roles"] == ["DIRECTOR"]

        assert client.get("/api/v1/whoami").status_code == 200
        workspaces = client.get("/api/v1/workspaces")
        assert workspaces.status_code == 200
        assert workspaces.json() == [
            {
                "workspace_id": str(bootstrap.workspace_id),
                "workspace_key": "ALOS_GOVERNANCE",
                "name": "ALOS Governance",
                "division_code": "IT",
                "access_level": "OWNER",
            }
        ]
        policy = client.get("/api/v1/governance/model-policy")
        assert policy.status_code == 200
        assert policy.json() == {
            "provider": "disabled",
            "model_light": "",
            "model_standard": "",
            "model_critical": "",
            "max_output_tokens": 1200,
        }
        budget = client.get(f"/api/v1/workspaces/{bootstrap.workspace_id}/budget")
        assert budget.status_code == 200
        assert budget.json()["daily_request_limit"] == 2
        assert budget.json()["daily_output_token_limit"] == 2400
        assert budget.json()["daily_cost_cap_usd"] == "0.2500"

        updated = client.put(
            f"/api/v1/workspaces/{bootstrap.workspace_id}/budget",
            json={
                "daily_request_limit": 3,
                "daily_output_token_limit": 3_600,
                "daily_cost_cap_usd": "0.30",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["daily_request_limit"] == 3
        audit = client.get(
            f"/api/v1/audit-events?workspace_id={bootstrap.workspace_id}&limit=10"
        )
        assert audit.status_code == 200
        assert {event["action"] for event in audit.json()} == {
            "DIRECTOR_CREDENTIAL_BOOTSTRAPPED",
            "COST_LIMIT_UPDATED",
        }

        local_token = client.post(
            "/api/v1/auth/local-token",
            json={
                "user_id": str(uuid4()),
                "organization_id": str(uuid4()),
                "roles": ["DIRECTOR"],
            },
        )
        assert local_token.status_code == 403
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
