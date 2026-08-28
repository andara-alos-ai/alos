import pytest
from pydantic import ValidationError

from alos.config import Settings


def test_staging_rejects_default_signing_secret() -> None:
    with pytest.raises(ValidationError, match="wajib unik dan kuat"):
        Settings(environment="staging")


def test_signing_secret_has_minimum_length() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_signing_secret="too-short")


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="prod")  # type: ignore[arg-type]
