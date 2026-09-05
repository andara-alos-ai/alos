from decimal import ROUND_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LlmProvider = Literal["disabled", "openai", "anthropic", "gemini", "local"]
ModelRoute = Literal["light", "standard", "critical"]


# Text-token rates per one million tokens. They are deliberately kept on the
# server so a browser cannot select a cheaper route or alter cost accounting.
# Refresh this registry together with the deployment when OpenAI changes a
# model's published pricing.
_OPENAI_TEXT_PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-5.6-luna": (Decimal("0.20"), Decimal("1.20")),
    "gpt-5.6-terra": (Decimal("2.00"), Decimal("12.00")),
    "gpt-5.6-sol": (Decimal("4.00"), Decimal("20.00")),
}
_COST_PRECISION = Decimal("0.000001")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Configuration deliberately limited to the ALOS staging boundary."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ALOS_", extra="ignore")

    application_name: str = "ALOS"
    environment: Environment = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://alos:change-me@127.0.0.1:5433/alos"

    auth_issuer: str = "alos-local"
    auth_audience: str = "alos-platform"
    auth_signing_secret: SecretStr = SecretStr("local-development-only-change-me")
    auth_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    object_storage_provider: Literal["filesystem", "s3"] = "filesystem"
    object_storage_bucket: str = "alos-documents"
    object_storage_path: Path = Path("./data/objects")
    object_storage_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)

    llm_provider: LlmProvider = "disabled"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    llm_model_light: str = ""
    llm_model_standard: str = ""
    llm_model_critical: str = ""
    llm_base_url: str | None = None
    llm_fallback_provider: Literal["disabled", "anthropic"] = "disabled"
    llm_fallback_api_key: SecretStr | None = None
    llm_fallback_model: str = ""
    llm_fallback_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    llm_store_responses: bool = False
    llm_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_output_tokens: int = Field(default=3_000, ge=256, le=128_000)
    llm_max_data_classification: Literal[
        "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"
    ] = "INTERNAL"
    llm_daily_request_limit: int = Field(default=500, ge=1)
    llm_daily_output_token_limit: int = Field(default=500_000, ge=1_000)
    llm_daily_cost_cap_usd: Decimal = Field(default=Decimal("5.00"), ge=0)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    budget_timezone: str = "Asia/Jakarta"

    repository_root: Path = Field(default_factory=repository_root)
    migrations_path: Path | None = None

    @model_validator(mode="after")
    def validate_security_boundary(self) -> "Settings":
        secret = self.auth_signing_secret.get_secret_value()
        if self.environment in {"staging", "production"} and (
            secret == "local-development-only-change-me" or len(secret) < 32
        ):
            raise ValueError("staging/production requires a unique signing secret")
        if self.environment == "production" and self.object_storage_provider != "s3":
            raise ValueError("production requires object storage outside the local filesystem")
        if self.llm_provider == "local" and self.environment not in {"local", "test"}:
            raise ValueError("local LLM is limited to local/test")
        if self.llm_provider == "gemini" and self.environment not in {"local", "test"}:
            raise ValueError("Gemini is limited to local/test")
        if self.environment == "production" and self.llm_provider not in {"disabled", "openai"}:
            raise ValueError("OpenAI is the only permitted primary production provider")
        if self.llm_provider != "disabled" and (
            self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip()
        ):
            raise ValueError("an enabled LLM provider requires an environment secret")
        if self.llm_provider != "disabled" and not self.llm_model.strip():
            raise ValueError("an enabled LLM provider requires a model policy")
        if self.llm_provider == "openai" and self.environment in {"staging", "production"}:
            configured_models = {
                model.strip()
                for model in (
                    self.llm_model,
                    self.llm_model_light,
                    self.llm_model_standard,
                    self.llm_model_critical,
                )
                if model.strip()
            }
            unknown_models = configured_models.difference(_OPENAI_TEXT_PRICING_PER_MILLION)
            if unknown_models:
                raise ValueError(
                    "OpenAI model pricing is not configured for the selected model route"
                )
        if self.environment in {"staging", "production"} and self.llm_store_responses:
            raise ValueError("staging/production must keep provider response storage disabled")
        return self

    def model_for_route(self, route: ModelRoute) -> str:
        """Resolve a Contract model route only from server-side configuration.

        A contract selects a bounded route, never a raw provider model name.
        Empty route overrides intentionally fall back to the configured primary
        model, which preserves the single-model Gemini local setup.
        """
        configured = {
            "light": self.llm_model_light,
            "standard": self.llm_model_standard,
            "critical": self.llm_model_critical,
        }[route]
        return configured.strip() or self.llm_model.strip()

    def estimate_llm_cost_usd(
        self, *, model: str, input_tokens: int, output_tokens: int
    ) -> Decimal:
        """Return a conservative text-token estimate rounded up for budget safety.

        Non-OpenAI test/local providers do not have a staging USD price table,
        so they remain zero-cost fixtures. OpenAI routes are validated during
        Settings construction and therefore cannot silently bypass this guard.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts cannot be negative")
        if self.llm_provider != "openai":
            return Decimal("0")
        pricing = _OPENAI_TEXT_PRICING_PER_MILLION.get(model)
        if pricing is None:
            raise ValueError("OpenAI model pricing is not configured")
        input_price, output_price = pricing
        estimated = (
            Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price
        ) / Decimal(1_000_000)
        return estimated.quantize(_COST_PRECISION, rounding=ROUND_UP)


@lru_cache
def get_settings() -> Settings:
    return Settings()
