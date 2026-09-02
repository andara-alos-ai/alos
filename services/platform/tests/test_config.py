import pytest

from alos.config import Settings


def test_staging_rejects_default_signing_secret() -> None:
    with pytest.raises(ValueError, match="unique signing secret"):
        Settings(environment="staging", auth_signing_secret="local-development-only-change-me")


def test_local_allows_disabled_model_gateway() -> None:
    settings = Settings(_env_file=None, environment="local", llm_provider="disabled")
    assert settings.llm_provider == "disabled"
