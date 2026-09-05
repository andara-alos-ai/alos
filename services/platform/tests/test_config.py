from decimal import Decimal
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


def test_local_allows_gemini_for_the_temporary_local_provider() -> None:
    settings = Settings(
        _env_file=None,
        environment="local",
        llm_provider="gemini",
        llm_api_key="test-only-key",
        llm_model="gemini-3.7-flash",
    )
    assert settings.llm_provider == "gemini"


def test_staging_rejects_gemini() -> None:
    with pytest.raises(ValueError, match="Gemini is limited"):
        Settings(
            _env_file=None,
            environment="staging",
            auth_signing_secret="a" * 32,
            llm_provider="gemini",
            llm_api_key="test-only-key",
            llm_model="gemini-3.7-flash",
        )


def test_config_allows_a_container_migrations_path() -> None:
    settings = Settings(_env_file=None, migrations_path="/app/infra/database")
    assert settings.migrations_path == Path("/app/infra/database")


def test_openai_pricing_estimate_rounds_up_for_a_hard_cost_cap() -> None:
    settings = Settings(
        _env_file=None,
        environment="staging",
        auth_signing_secret="a" * 32,
        llm_provider="openai",
        llm_api_key="test-only-key",
        llm_model="gpt-5.6-luna",
    )

    assert settings.estimate_llm_cost_usd(
        model="gpt-5.6-luna", input_tokens=12, output_tokens=9
    ) == Decimal("0.000014")


def test_staging_openai_rejects_an_unpriced_model_route() -> None:
    with pytest.raises(ValueError, match="pricing is not configured"):
        Settings(
            _env_file=None,
            environment="staging",
            auth_signing_secret="a" * 32,
            llm_provider="openai",
            llm_api_key="test-only-key",
            llm_model="unreviewed-model",
        )
