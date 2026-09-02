import re
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

    application_name: str = "ALOS"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://alos:change-me@localhost:5433/alos"
    llm_provider: Literal["disabled", "openai", "anthropic", "local"] = "disabled"
    llm_api_key: SecretStr | None = None
    llm_model: str = Field(default="", max_length=120)
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    llm_max_data_classification: Literal[
        "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"
    ] = "INTERNAL"
    llm_daily_request_limit: int = Field(default=500, ge=1, le=100_000)
    llm_daily_output_token_limit: int = Field(default=500_000, ge=1_000, le=100_000_000)
    auth_issuer: str = "alos-local"
    auth_audience: str = "alos-platform"
    auth_signing_secret: SecretStr = Field(
        default=SecretStr("local-development-only-change-me"), min_length=32
    )
    auth_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    session_cookie_name: str = Field(default="alos_session", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    csrf_cookie_name: str = Field(default="alos_csrf", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_secure: bool | None = None
    csrf_token_ttl_seconds: int = Field(default=86400, ge=300, le=604800)
    oidc_provider: Literal["disabled", "google"] = "disabled"
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str = "http://localhost:8000/api/v1/auth/oidc/callback/google"
    oidc_allowed_domain: str | None = None
    oidc_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)
    oidc_transaction_ttl_seconds: int = Field(default=600, ge=120, le=900)
    oidc_login_code_ttl_seconds: int = Field(default=60, ge=30, le=120)
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
    api_rate_limit_per_minute: int = Field(default=600, ge=10, le=100_000)
    auth_rate_limit_per_minute: int = Field(default=60, ge=5, le=10_000)
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
        if self.environment in {"staging", "production"} and self.session_cookie_secure is False:
            raise ValueError("Session cookie wajib Secure pada staging/production")
        if self.session_cookie_samesite == "none" and not self.is_session_cookie_secure:
            raise ValueError("SameSite=None hanya boleh digunakan bersama Secure cookie")
        self._validate_n8n_configuration()
        self._validate_llm_configuration()
        self._validate_oidc_configuration()
        return self

    def _validate_oidc_configuration(self) -> None:
        if self.oidc_provider == "disabled":
            return
        client_id = (self.oidc_client_id or "").strip()
        client_secret = self.oidc_client_secret_value
        if not client_id or not client_secret:
            raise ValueError("OIDC aktif memerlukan Client ID dan Client Secret")
        if len(client_id) > 512 or len(client_secret) > 512:
            raise ValueError("Credential OIDC melebihi batas yang diizinkan")
        allowed_domain = (self.oidc_allowed_domain or "").strip().casefold()
        domain_pattern = (
            r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
        )
        if allowed_domain and re.fullmatch(domain_pattern, allowed_domain) is None:
            raise ValueError("Domain OIDC yang diizinkan tidak valid")
        redirect = urlsplit(self.oidc_redirect_uri)
        if redirect.scheme not in {"http", "https"} or not redirect.hostname:
            raise ValueError("Redirect URI OIDC bukan URL HTTP(S) yang valid")
        if redirect.username or redirect.password or redirect.query or redirect.fragment:
            raise ValueError(
                "Redirect URI OIDC tidak boleh memuat credential, query, atau fragment"
            )
        web_origin = urlsplit(self.web_origin)
        if web_origin.scheme not in {"http", "https"} or not web_origin.hostname:
            raise ValueError("Web origin ALOS bukan URL HTTP(S) yang valid")
        if (
            web_origin.username
            or web_origin.password
            or web_origin.query
            or web_origin.fragment
            or web_origin.path not in {"", "/"}
        ):
            raise ValueError("Web origin ALOS wajib berupa origin tanpa path atau credential")
        if (
            self.environment in {"staging", "production"}
            and (redirect.scheme != "https" or web_origin.scheme != "https")
        ):
            raise ValueError("OIDC staging/production wajib menggunakan HTTPS")

    def _validate_llm_configuration(self) -> None:
        if self.llm_provider == "disabled":
            return
        if self.llm_provider in {"openai", "anthropic"} and (
            self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip()
        ):
            raise ValueError("LLM provider aktif memerlukan ALOS_LLM_API_KEY")
        if not self.llm_model.strip():
            raise ValueError("LLM provider aktif memerlukan ALOS_LLM_MODEL")
        if self.llm_base_url:
            parsed = urlsplit(self.llm_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("ALOS_LLM_BASE_URL bukan URL HTTP(S) yang valid")
            if parsed.username or parsed.password or parsed.fragment:
                raise ValueError("ALOS_LLM_BASE_URL tidak boleh memuat credential atau fragment")
            if self.environment in {"staging", "production"} and parsed.scheme != "https":
                raise ValueError("Endpoint LLM staging/production wajib HTTPS")

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
    def oidc_client_secret_value(self) -> str | None:
        if self.oidc_client_secret is None:
            return None
        value = self.oidc_client_secret.get_secret_value().strip()
        return value or None

    @property
    def effective_api_rate_limit_per_minute(self) -> int:
        """Avoid cross-test throttling while preserving configured deployed limits."""

        if self.environment in {"local", "test"}:
            return max(self.api_rate_limit_per_minute, 100_000)
        return self.api_rate_limit_per_minute

    @property
    def effective_auth_rate_limit_per_minute(self) -> int:
        """Use a high local ceiling; staging and production remain explicitly limited."""

        if self.environment in {"local", "test"}:
            return max(self.auth_rate_limit_per_minute, 10_000)
        return self.auth_rate_limit_per_minute

    @property
    def is_session_cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.environment in {"staging", "production"}

    @property
    def max_request_body_bytes(self) -> int:
        return self.object_storage_max_upload_bytes + 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
