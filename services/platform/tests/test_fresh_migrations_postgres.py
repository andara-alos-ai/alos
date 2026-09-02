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
        )
        with psycopg.connect(temporary_url) as connection:
            assert connection.execute("SELECT count(*) FROM identity.divisions").fetchone() == (6,)
            assert connection.execute("SELECT count(*) FROM audit.events").fetchone() == (0,)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(database_name)))
