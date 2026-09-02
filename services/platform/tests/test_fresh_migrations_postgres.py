import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.config import get_settings
from alos.persistence.migrations import apply_migrations, psycopg_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_all_migrations_apply_to_a_fresh_database() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_release_gate_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"

    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        applied = apply_migrations(temporary_url, REPOSITORY_ROOT / "infra" / "database")
        assert len(applied) == 42
        with psycopg.connect(temporary_url) as connection:
            assert (
                connection.execute("SELECT count(*) FROM platform.schema_migrations").fetchone()[0]
                    == 42
            )
            constraint_exists = connection.execute(
                """
                SELECT 1 FROM pg_constraint
                WHERE conname = 'documents_division_organization_fk'
                """
            ).fetchone()
            assert constraint_exists is not None
            reservation_evidence_column = connection.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'sales' AND table_name = 'reservations'
                  AND column_name = 'evidence_document_version_id'
                """
            ).fetchone()
            assert reservation_evidence_column is not None
            scoped_references = {
                "reservations_organization_reference_key": (
                    "UNIQUE (organization_id, reservation_reference)"
                ),
                "payment_records_organization_reference_key": (
                    "UNIQUE (organization_id, payment_reference)"
                ),
                "reconciliations_organization_reference_key": (
                    "UNIQUE (organization_id, transaction_reference)"
                ),
            }
            for constraint_name, expected_definition in scoped_references.items():
                definition = connection.execute(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
                    (constraint_name,),
                ).fetchone()
                assert definition is not None
                assert definition[0] == expected_definition
            assert connection.execute(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'payment_requests_approval_route_check'"
            ).fetchone() is not None
            assert connection.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'uat' AND table_name = 'signoffs'"
            ).fetchone() is not None
            for constraint_name in (
                "reservations_organization_lead_fkey",
                "payment_records_organization_request_fkey",
                "reconciliations_organization_request_fkey",
                "reconciliations_organization_record_fkey",
            ):
                assert connection.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (constraint_name,),
                ).fetchone() is not None
            assert connection.execute(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'audit_entries_append_only'"
            ).fetchone() is not None
            assert connection.execute(
                "SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'audit_chain_legacy_exceptions_append_only'"
            ).fetchone() is not None
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
