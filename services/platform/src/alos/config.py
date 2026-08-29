from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ALOS_",
        extra="ignore",
    )

    application_name: str = "ALOS Internal v1"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://alos:change-me@localhost:5433/alos"
    llm_provider: str = "disabled"
    auth_issuer: str = "alos-local"
    auth_audience: str = "alos-internal"
    auth_signing_secret: SecretStr = Field(
        default=SecretStr("local-development-only-change-me"), min_length=32
    )
    auth_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    object_storage_provider: Literal["filesystem", "s3"] = "filesystem"
    object_storage_bucket: str = Field(
        default="alos-documents", pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
    )
    object_storage_path: Path = Path("./data/objects")
    object_storage_endpoint_url: str | None = None
    object_storage_region: str = Field(default="us-east-1", min_length=3, max_length=40)
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    object_storage_max_upload_bytes: int = Field(
        default=25 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024
    )
    document_scan_mode: Literal["disabled", "external"] = "disabled"
    worker_poll_seconds: int = Field(default=5, ge=1, le=300)
    worker_batch_size: int = Field(default=50, ge=1, le=500)
    worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    worker_max_attempts: int = Field(default=5, ge=1, le=20)
    deadline_horizon_minutes: int = Field(default=1440, ge=1, le=10080)
    escalation_interval_minutes: int = Field(default=60, ge=15, le=1440)
    n8n_enabled: bool = False
    n8n_webhook_url: str | None = None
    n8n_webhook_secret: SecretStr | None = None
    n8n_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)
    repository_root: Path = Field(default_factory=default_repository_root)

    @model_validator(mode="after")
    def reject_insecure_production_configuration(self) -> "Settings":
        if self.environment in {"staging", "production"}:
            secret = self.auth_signing_secret.get_secret_value()
            if secret == "local-development-only-change-me" or len(set(secret)) < 12:  # noqa: S105
                raise ValueError(
                    "ALOS_AUTH_SIGNING_SECRET wajib unik dan kuat pada staging/production"
                )
        if self.environment == "production" and self.object_storage_provider == "filesystem":
            raise ValueError("Production wajib menggunakan object storage provider s3")
        if self.environment == "production" and self.document_scan_mode == "disabled":
            raise ValueError("Production wajib mengaktifkan pemeriksaan malware dokumen")
        if (
            self.environment == "production"
            and self.object_storage_endpoint is not None
            and not self.object_storage_endpoint.startswith("https://")
        ):
            raise ValueError("Endpoint object storage production wajib menggunakan HTTPS")
        access_key = self.object_storage_access_key_value
        secret_key = self.object_storage_secret_key_value
        if bool(access_key) != bool(secret_key):
            raise ValueError("Access key dan secret key object storage harus diberikan bersama")
        self._validate_n8n_configuration()
        return self

    def _validate_n8n_configuration(self) -> None:
        url = (self.n8n_webhook_url or "").strip()
        secret = self.n8n_webhook_secret_value
        if not self.n8n_enabled:
            return
        if not url or not secret:
            raise ValueError("n8n aktif memerlukan webhook URL dan signing secret")
        if len(secret) < 32:
            raise ValueError("Signing secret n8n wajib minimal 32 karakter")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Webhook n8n wajib menggunakan URL HTTP(S) yang valid")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Webhook n8n tidak boleh memuat credential atau fragment pada URL")
        if self.environment in {"staging", "production"} and parsed.scheme != "https":
            raise ValueError("Webhook n8n staging/production wajib menggunakan HTTPS")

    @property
    def definitions_root(self) -> Path:
        return self.repository_root / "definitions"

    @property
    def resolved_object_storage_path(self) -> Path:
        if self.object_storage_path.is_absolute():
            return self.object_storage_path.resolve()
        return (self.repository_root / self.object_storage_path).resolve()

    @property
    def object_storage_endpoint(self) -> str | None:
        value = (self.object_storage_endpoint_url or "").strip()
        return value or None

    @property
    def object_storage_access_key_value(self) -> str | None:
        if self.object_storage_access_key is None:
            return None
        value = self.object_storage_access_key.get_secret_value().strip()
        return value or None

    @property
    def object_storage_secret_key_value(self) -> str | None:
        if self.object_storage_secret_key is None:
            return None
        value = self.object_storage_secret_key.get_secret_value().strip()
        return value or None

    @property
    def n8n_webhook_secret_value(self) -> str | None:
        if self.n8n_webhook_secret is None:
            return None
        value = self.n8n_webhook_secret.get_secret_value().strip()
        return value or None

    @property
    def max_request_body_bytes(self) -> int:
        return self.object_storage_max_upload_bytes + 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
