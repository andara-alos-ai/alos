import hashlib
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.config import get_settings
from alos.executive_dashboard import ExecutiveDashboardRepository
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_snapshot_aggregates_only_accessible_persisted_approvals() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_executive_dashboard_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        context = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        content = "Dokumen pengujian dashboard eksekutif."
        with psycopg.connect(temporary_url) as connection:
            document = connection.execute(
                """
                INSERT INTO documents.records (
                    organization_id, workspace_id, division_id, title, category,
                    classification, origin, status, owner_user_id, created_by_user_id
                )
                SELECT %s, workspace_id, division_id, 'Executive Dashboard Evidence',
                       'GOVERNANCE', 'INTERNAL', 'MANUAL', 'IN_REVIEW', %s, %s
                FROM workspace.workspaces WHERE workspace_id = %s
                RETURNING document_id
                """,
                (
                    context.organization_id,
                    context.user_id,
                    context.user_id,
                    context.workspace_id,
                ),
            ).fetchone()
            assert document is not None
            version = connection.execute(
                """
                INSERT INTO documents.versions (
                    document_id, version_number, content, content_sha256,
                    created_by_user_id
                ) VALUES (%s, 1, %s, %s, %s)
                RETURNING document_version_id
                """,
                (
                    document[0],
                    content,
                    hashlib.sha256(content.encode()).hexdigest(),
                    context.user_id,
                ),
            ).fetchone()
            assert version is not None
            connection.execute(
                """
                INSERT INTO documents.review_requests (
                    document_id, document_version_id, submitted_by_user_id
                ) VALUES (%s, %s, %s)
                """,
                (document[0], version[0], context.user_id),
            )

        snapshot = ExecutiveDashboardRepository(temporary_url).snapshot(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            workspace_ids=[context.workspace_id],
        )

        approval_metric = next(
            metric for metric in snapshot.metrics if metric.key == "pending_approvals"
        )
        assert approval_metric.value == 1
        assert snapshot.pending_approvals[0].title == "Executive Dashboard Evidence"
        assert snapshot.pending_approvals[0].kind == "DOCUMENT"
        it_summary = next(
            division for division in snapshot.divisions if division.division_code == "IT"
        )
        assert it_summary.document_count == 1
        assert it_summary.pending_approvals == 1
        assert it_summary.health == "ATTENTION"
        assert snapshot.project_distribution.available is False
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name))
            )
