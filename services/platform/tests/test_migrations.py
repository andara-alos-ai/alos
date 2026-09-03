from pathlib import Path

from alos.persistence.migrations import discover_migrations


def test_hari_1_migrations_are_ordered_and_complete() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    migrations = discover_migrations(repository_root / "infra" / "database")
    assert [migration.name for migration in migrations] == [
        "001_genesis_mvp1_baseline.sql",
        "002_h1_policy_and_test_registry.sql",
        "003_h2_agent_registry.sql",
        "004_h3_runtime_budget.sql",
        "005_h4_release_governance.sql",
    ]
