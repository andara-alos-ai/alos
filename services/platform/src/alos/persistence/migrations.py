import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg

from alos.config import get_settings


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        migrations.append(
            Migration(
                version=path.name.split("_", 1)[0],
                name=path.name,
                path=path,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("Versi migrasi database harus unik")
    return tuple(migrations)


def psycopg_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def apply_migrations(database_url: str, directory: Path) -> tuple[str, ...]:
    applied_now: list[str] = []
    with psycopg.connect(psycopg_url(database_url), autocommit=False) as connection:
        connection.execute("SELECT pg_advisory_lock(hashtext('alos-schema-migrations'))")
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
                row = connection.execute(
                    "SELECT checksum FROM platform.schema_migrations WHERE version = %s",
                    (migration.version,),
                ).fetchone()
                if row is not None:
                    if row[0] != migration.checksum:
                        raise RuntimeError(
                            f"Checksum migrasi {migration.name} berubah setelah diterapkan"
                        )
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
            connection.execute("SELECT pg_advisory_unlock(hashtext('alos-schema-migrations'))")
            connection.commit()
    return tuple(applied_now)


def main() -> None:
    settings = get_settings()
    directory = settings.repository_root / "infra" / "database"
    applied = apply_migrations(settings.database_url, directory)
    if applied:
        print(f"Migrasi diterapkan: {', '.join(applied)}")
    else:
        print("Database sudah menggunakan migrasi terbaru")


if __name__ == "__main__":
    main()
