from unittest.mock import MagicMock

from alos.persistence import database


def test_database_readiness_uses_a_bounded_connection_timeout(monkeypatch) -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (1,)
    captured: dict[str, object] = {}

    def connect(url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(database.psycopg, "connect", connect)

    assert database.database_is_ready("postgresql+psycopg://alos:password@127.0.0.1:5433/alos")
    assert captured == {
        "url": "postgresql://alos:password@127.0.0.1:5433/alos",
        "connect_timeout": 5,
    }
