import pytest
from pydantic import ValidationError

from alos.config import Settings


def test_staging_rejects_default_signing_secret() -> None:
    with pytest.raises(ValidationError, match="wajib unik dan kuat"):
        Settings(
            environment="staging",
            auth_signing_secret="local-development-only-change-me",
        )


def test_signing_secret_has_minimum_length() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_signing_secret="too-short")


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="prod")  # type: ignore[arg-type]


def test_production_rejects_local_document_storage() -> None:
    with pytest.raises(ValidationError, match="object storage provider s3"):
        Settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            document_scan_mode="external",
        )


def test_production_requires_document_malware_scanning() -> None:
    with pytest.raises(ValidationError, match="pemeriksaan malware"):
        Settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            object_storage_provider="s3",
        )


def test_object_storage_credentials_must_be_a_pair() -> None:
    with pytest.raises(ValidationError, match="diberikan bersama"):
        Settings(object_storage_access_key="access-key-only")


def test_production_object_storage_endpoint_requires_https() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            environment="production",
            auth_signing_secret="production-signing-secret-value-9X7q2L",
            object_storage_provider="s3",
            object_storage_endpoint_url="http://storage.internal:9000",
            document_scan_mode="external",
        )


def test_enabled_n8n_requires_url_and_secret() -> None:
    with pytest.raises(ValidationError, match="webhook URL dan signing secret"):
        Settings(n8n_enabled=True)


def test_n8n_rejects_short_secret_and_url_credentials() -> None:
    with pytest.raises(ValidationError, match="minimal 32"):
        Settings(
            n8n_enabled=True,
            n8n_webhook_url="http://localhost:5678/webhook/alos",
            n8n_webhook_secret="short-secret",
        )
    with pytest.raises(ValidationError, match="credential"):
        Settings(
            n8n_enabled=True,
            n8n_webhook_url="https://user:password@n8n.example.test/webhook/alos",
            n8n_webhook_secret="secure-n8n-signing-secret-value-123456",
        )


def test_staging_n8n_requires_https() -> None:
    with pytest.raises(ValidationError, match="n8n staging/production"):
        Settings(
            environment="staging",
            auth_signing_secret="staging-signing-secret-value-9X7q2L",
            n8n_enabled=True,
            n8n_webhook_url="http://n8n.internal/webhook/alos",
            n8n_webhook_secret="secure-n8n-signing-secret-value-123456",
        )
