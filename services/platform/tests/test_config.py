from pathlib import Path

import pytest

from alos.config import Settings


def test_staging_rejects_default_signing_secret() -> None:
    with pytest.raises(ValueError, match="unique signing secret"):
        Settings(environment="staging", auth_signing_secret="local-development-only-change-me")


def test_local_allows_disabled_model_gateway() -> None:
    settings = Settings(_env_file=None, environment="local", llm_provider="disabled")
    assert settings.llm_provider == "disabled"


def test_staging_openai_requires_a_model_policy() -> None:
    with pytest.raises(ValueError, match="model policy"):
        Settings(
            _env_file=None,
            environment="staging",
            auth_signing_secret="a" * 32,
            llm_provider="openai",
            llm_api_key="test-only-key",
        )


def test_staging_disables_provider_response_storage() -> None:
    with pytest.raises(ValueError, match="response storage"):
        Settings(
            _env_file=None,
            environment="staging",
            auth_signing_secret="a" * 32,
            llm_provider="openai",
            llm_api_key="test-only-key",
            llm_model="gpt-5.6-terra",
            llm_store_responses=True,
        )


def test_config_allows_a_container_migrations_path() -> None:
    settings = Settings(_env_file=None, migrations_path="/app/infra/database")
    assert settings.migrations_path == Path("/app/infra/database")
