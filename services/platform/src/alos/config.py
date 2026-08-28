from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    database_url: str = "postgresql+psycopg://alos:change-me@localhost:5432/alos"
    llm_provider: str = "disabled"
    repository_root: Path = Field(default_factory=default_repository_root)

    @property
    def definitions_root(self) -> Path:
        return self.repository_root / "definitions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
