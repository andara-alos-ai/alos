import psycopg


def psycopg_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def database_is_ready(database_url: str) -> bool:
    try:
        with psycopg.connect(psycopg_url(database_url), connect_timeout=5) as connection:
            return connection.execute("SELECT 1").fetchone() == (1,)
    except psycopg.Error:
        return False
