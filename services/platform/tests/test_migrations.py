from pathlib import Path

from alos.persistence.migrations import discover_migrations


def test_genesis_mvp1_starts_from_one_clean_baseline() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    migrations = discover_migrations(repository_root / "infra" / "database")
    assert [migration.name for migration in migrations] == ["001_genesis_mvp1_baseline.sql"]
