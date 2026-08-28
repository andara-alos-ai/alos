from functools import lru_cache
from pathlib import Path

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
    environment: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://alos:change-me@localhost:5433/alos"
    llm_provider: str = "disabled"
    auth_issuer: str = "alos-local"
    auth_audience: str = "alos-internal"
    auth_signing_secret: SecretStr = SecretStr("local-development-only-change-me")
    auth_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    repository_root: Path = Field(default_factory=default_repository_root)

    @model_validator(mode="after")
    def reject_insecure_production_configuration(self) -> "Settings":
        if (
            self.environment == "production"
            and self.auth_signing_secret.get_secret_value() == "local-development-only-change-me"
        ):
            raise ValueError("ALOS_AUTH_SIGNING_SECRET wajib diganti pada production")
        return self

    @property
    def definitions_root(self) -> Path:
        return self.repository_root / "definitions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
