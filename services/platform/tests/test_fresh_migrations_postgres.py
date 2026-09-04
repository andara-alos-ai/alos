import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.config import get_settings
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_clean_baseline_applies_to_a_fresh_database() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_genesis_gate_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        assert apply_migrations(temporary_url, repository_root / "infra" / "database") == (
            "001_genesis_mvp1_baseline.sql",
            "002_h1_policy_and_test_registry.sql",
            "003_h2_agent_registry.sql",
            "004_h3_runtime_budget.sql",
            "005_h4_release_governance.sql",
            "006_h5_source_evidence.sql",
            "007_h5_tool_permission_approvals.sql",
            "008_h6_staging_authentication.sql",
            "009_h5_source_vault_policy.sql",
        )
        with psycopg.connect(temporary_url) as connection:
            assert connection.execute("SELECT count(*) FROM identity.divisions").fetchone() == (6,)
            assert connection.execute("SELECT count(*) FROM audit.events").fetchone() == (0,)
            assert connection.execute(
                "SELECT to_regclass('agents.tool_definitions')"
            ).fetchone() == ("agents.tool_definitions",)
            assert connection.execute(
                "SELECT to_regclass('governance.permission_policies')"
            ).fetchone() == ("governance.permission_policies",)
            assert connection.execute("SELECT to_regclass('governance.test_cases')").fetchone() == (
                "governance.test_cases",
            )
            assert connection.execute("SELECT to_regclass('governance.test_runs')").fetchone() == (
                "governance.test_runs",
            )
            assert connection.execute(
                "SELECT tgname FROM pg_trigger WHERE tgname = 'agents_contract_parent_guard'"
            ).fetchone() == ("agents_contract_parent_guard",)
            assert connection.execute(
                "SELECT to_regclass('runtime.budget_reservations')"
            ).fetchone() == ("runtime.budget_reservations",)
            assert connection.execute(
                "SELECT to_regclass('governance.agent_change_requests')"
            ).fetchone() == ("governance.agent_change_requests",)
            assert connection.execute(
                "SELECT to_regclass('sources.content_chunks')"
            ).fetchone() == ("sources.content_chunks",)
            assert connection.execute(
                "SELECT to_regclass('sources.vault_policies')"
            ).fetchone() == ("sources.vault_policies",)
            assert connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'governance' AND table_name = 'permission_policies'
                  AND column_name = 'approved_by_user_id'
                """
            ).fetchone() == ("approved_by_user_id",)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(database_name)))
