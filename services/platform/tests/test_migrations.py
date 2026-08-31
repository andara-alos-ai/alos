from pathlib import Path

from alos.persistence.migrations import discover_migrations, psycopg_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_database_migrations_are_ordered_and_unique() -> None:
    migrations = discover_migrations(REPOSITORY_ROOT / "infra" / "database")

    assert [migration.version for migration in migrations] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
        "007",
        "008",
        "009",
        "010",
        "011",
        "012",
        "013",
        "014",
        "015",
        "016",
        "017",
        "018",
        "019",
        "020",
        "021",
        "022",
        "023",
        "024",
        "025",
        "026",
    ]
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_sqlalchemy_postgres_url_is_converted_for_psycopg() -> None:
    result = psycopg_url("postgresql+psycopg://alos:secret@localhost:5432/alos")

    assert result == "postgresql://alos:secret@localhost:5432/alos"
