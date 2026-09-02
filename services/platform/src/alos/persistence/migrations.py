import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg

from alos.config import get_settings
from alos.persistence.database import psycopg_url


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    migrations = tuple(
        Migration(
            version=path.name.split("_", 1)[0],
            name=path.name,
            path=path,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
        if path.is_file()
    )
    versions = [migration.version for migration in migrations]
    if not migrations:
        raise ValueError("at least one Genesis MVP1 migration is required")
    if len(versions) != len(set(versions)):
        raise ValueError("migration versions must be unique")
    return migrations


def apply_migrations(database_url: str, directory: Path) -> tuple[str, ...]:
    applied_now: list[str] = []
    with psycopg.connect(psycopg_url(database_url), autocommit=False) as connection:
        connection.execute("SELECT pg_advisory_lock(hashtext('alos-genesis-migrations'))")
        try:
            connection.execute("CREATE SCHEMA IF NOT EXISTS platform")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS platform.schema_migrations (
                    version text PRIMARY KEY,
                    name text NOT NULL UNIQUE,
                    checksum char(64) NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            connection.commit()
            for migration in discover_migrations(directory):
                existing = connection.execute(
                    "SELECT checksum FROM platform.schema_migrations WHERE version = %s",
                    (migration.version,),
                ).fetchone()
                if existing is not None:
                    if existing[0] != migration.checksum:
                        raise RuntimeError(f"applied migration changed: {migration.name}")
                    continue
                connection.execute(migration.path.read_text(encoding="utf-8"))
                connection.execute(
                    """
                    INSERT INTO platform.schema_migrations (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
                connection.commit()
                applied_now.append(migration.name)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext('alos-genesis-migrations'))")
            connection.commit()
    return tuple(applied_now)


def main() -> None:
    settings = get_settings()
    migration_directory = settings.repository_root / "infra" / "database"
    applied = apply_migrations(settings.database_url, migration_directory)
    print("Database is current" if not applied else f"Applied: {', '.join(applied)}")


if __name__ == "__main__":
    main()
