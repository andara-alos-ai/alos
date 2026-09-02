from typing import Any

import pytest
from pydantic import ValidationError

from alos.config import Settings


def isolated_settings(**values: Any) -> Settings:
    values.setdefault("oidc_provider", "disabled")
    return Settings(_env_file=None, **values)


def test_default_product_name_and_security_namespace_use_alos_brand() -> None:
    settings = isolated_settings()

    assert settings.application_name == "ALOS"
    assert settings.auth_audience == "alos-platform"


def test_staging_rejects_default_signing_secret() -> None:
    with pytest.raises(ValidationError, match="wajib unik dan kuat"):
        isolated_settings(
            environment="staging",
            auth_signing_secret="local-development-only-change-me",
        )


def test_signing_secret_has_minimum_length() -> None:
    with pytest.raises(ValidationError):
        isolated_settings(auth_signing_secret="too-short")


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        isolated_settings(environment="prod")  # type: ignore[arg-type]


def test_production_rejects_local_document_storage() -> None:
    with pytest.raises(ValidationError, match="object storage provider s3"):
        isolated_settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            document_scan_mode="external",
        )


def test_production_requires_document_malware_scanning() -> None:
    with pytest.raises(ValidationError, match="pemeriksaan malware"):
        isolated_settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            object_storage_provider="s3",
        )


def test_object_storage_credentials_must_be_a_pair() -> None:
    with pytest.raises(ValidationError, match="diberikan bersama"):
        isolated_settings(object_storage_access_key="access-key-only")


def test_production_object_storage_endpoint_requires_https() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        isolated_settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            object_storage_provider="s3",
            object_storage_endpoint_url="http://storage.internal:9000",
            document_scan_mode="external",
        )


def test_enabled_n8n_requires_url_and_secret() -> None:
    with pytest.raises(ValidationError, match="webhook URL dan signing secret"):
        isolated_settings(n8n_enabled=True)


def test_n8n_rejects_short_secret_and_url_credentials() -> None:
    with pytest.raises(ValidationError, match="minimal 32"):
        isolated_settings(
            n8n_enabled=True,
            n8n_webhook_url="http://localhost:5678/webhook/alos",
            n8n_webhook_secret="short-secret",
        )
    with pytest.raises(ValidationError, match="credential"):
        isolated_settings(
            n8n_enabled=True,
            n8n_webhook_url="https://user:password@n8n.example.test/webhook/alos",
            n8n_webhook_secret="secure-n8n-signing-secret-value-123456",
        )


def test_staging_n8n_requires_https() -> None:
    with pytest.raises(ValidationError, match="n8n staging/production"):
        isolated_settings(
            environment="staging",
            auth_signing_secret="staging-signing-secret-value-9X7q2L",
            n8n_enabled=True,
            n8n_webhook_url="http://n8n.internal/webhook/alos",
            n8n_webhook_secret="secure-n8n-signing-secret-value-123456",
        )


def test_enabled_oidc_requires_client_credentials() -> None:
    with pytest.raises(ValidationError, match="Client ID dan Client Secret"):
        isolated_settings(oidc_provider="google")


def test_staging_oidc_requires_https() -> None:
    with pytest.raises(ValidationError, match="OIDC staging/production"):
        isolated_settings(
            environment="staging",
            auth_signing_secret="staging-signing-secret-value-9X7q2L",
            oidc_provider="google",
            oidc_client_id="client.apps.googleusercontent.com",
            oidc_client_secret="synthetic-client-secret",
            oidc_redirect_uri="http://localhost:8000/api/v1/auth/oidc/callback/google",
            web_origin="http://localhost:3000",
        )


def test_local_google_oidc_accepts_registered_localhost_callback() -> None:
    settings = isolated_settings(
        oidc_provider="google",
        oidc_client_id="client.apps.googleusercontent.com",
        oidc_client_secret="synthetic-client-secret",
    )

    assert settings.oidc_redirect_uri.endswith("/auth/oidc/callback/google")
    assert settings.oidc_client_secret_value == "synthetic-client-secret"


def test_samesite_none_requires_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="SameSite=None"):
        isolated_settings(session_cookie_samesite="none")
