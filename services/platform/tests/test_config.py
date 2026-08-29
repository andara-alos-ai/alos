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
