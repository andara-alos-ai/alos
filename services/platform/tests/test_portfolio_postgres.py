import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.config import get_settings
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.portfolio import PortfolioRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_portfolio_snapshots_are_derived_from_accessible_persisted_rows() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_portfolio_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        context = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        with psycopg.connect(temporary_url) as connection:
            division = connection.execute(
                "SELECT division_id FROM workspace.workspaces WHERE workspace_id = %s",
                (context.workspace_id,),
            ).fetchone()
            assert division is not None
            project = connection.execute(
                """
                INSERT INTO portfolio.projects (
                    organization_id, workspace_id, division_id, code, name, category,
                    owner_user_id, status, progress_percent, start_date, deadline,
                    budget_planned, budget_spent, overdue_tasks, created_by_user_id
                ) VALUES (
                    %s, %s, %s, 'ALOS-PLATFORM', 'ALOS Platform', 'Technology',
                    %s, 'AT_RISK', 62.5, '2026-01-01', '2026-12-31',
                    100000000, 62500000, 2, %s
                ) RETURNING project_id
                """,
                (
                    context.organization_id,
                    context.workspace_id,
                    division[0],
                    context.user_id,
                    context.user_id,
                ),
            ).fetchone()
            assert project is not None
            connection.execute(
                """
                INSERT INTO portfolio.project_progress_history (
                    project_id, recorded_on, progress_percent, status, recorded_by_user_id
                ) VALUES (%s, '2026-09-01', 62.5, 'AT_RISK', %s)
                """,
                (project[0], context.user_id),
            )
            connection.execute(
                """
                INSERT INTO portfolio.project_milestones (
                    project_id, title, due_date, status
                ) VALUES (%s, 'Release staging', '2026-09-30', 'AT_RISK')
                """,
                (project[0],),
            )
            connection.execute(
                """
                INSERT INTO portfolio.division_issues (
                    organization_id, workspace_id, division_id, project_id, title,
                    severity, status, owner_user_id, due_date, created_by_user_id
                ) VALUES (
                    %s, %s, %s, %s, 'Staging readiness', 'HIGH', 'OPEN',
                    %s, '2026-09-20', %s
                )
                """,
                (
                    context.organization_id,
                    context.workspace_id,
                    division[0],
                    project[0],
                    context.user_id,
                    context.user_id,
                ),
            )

        repository = PortfolioRepository(temporary_url)
        projects = repository.project_portfolio(
            organization_id=context.organization_id,
            workspace_ids=[context.workspace_id],
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
        )
        divisions = repository.divisions_overview(
            organization_id=context.organization_id,
            workspace_ids=[context.workspace_id],
        )

        assert projects.metrics.total == 1
        assert projects.metrics.at_risk == 1
        assert projects.projects[0].name == "ALOS Platform"
        assert projects.projects[0].owner_name
        assert projects.milestones[0].title == "Release staging"
        it_division = next(item for item in divisions.divisions if item.division_code == "IT")
        assert it_division.active_projects == 1
        assert it_division.average_progress == 62.5
        assert it_division.overdue_tasks == 2
        assert it_division.health == "ATTENTION"
        assert divisions.issues[0].title == "Staging readiness"
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
