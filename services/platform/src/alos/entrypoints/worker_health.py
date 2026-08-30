from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from alos.config import get_settings
from alos.persistence import Database


def worker_is_healthy(
    database_url: str,
    *,
    worker_name: str = "alos-operational-worker",
    max_age_seconds: int = 60,
) -> bool:
    """Return true only when the worker has a recent database heartbeat."""

    try:
        database = Database(database_url)
        with database.engine.connect() as connection:
            return bool(
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM observability.worker_runs
                            WHERE worker_name = :worker_name
                              AND (
                                  (
                                      status IN ('COMPLETED', 'PARTIAL')
                                      AND completed_at >= now() - make_interval(
                                          secs => :max_age_seconds
                                      )
                                  )
                                  OR (
                                      status = 'RUNNING'
                                      AND started_at >= now() - make_interval(
                                          secs => :max_age_seconds
                                      )
                                  )
                              )
                        )
                        """
                    ),
                    {
                        "worker_name": worker_name,
                        "max_age_seconds": max_age_seconds,
                    },
                ).scalar_one()
            )
    except SQLAlchemyError:
        return False


def main() -> None:
    settings = get_settings()
    max_age_seconds = max(60, settings.worker_poll_seconds * 4)
    raise SystemExit(
        0
        if worker_is_healthy(
            settings.database_url,
            max_age_seconds=max_age_seconds,
        )
        else 1
    )


if __name__ == "__main__":
    main()
