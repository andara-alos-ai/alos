from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LlmProvider = str
ModelRoute = Literal["light", "standard", "critical"]


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
    api_max_request_bytes: int = Field(default=30 * 1024 * 1024, ge=1024)
    api_rate_limit_per_minute: int = Field(default=300, ge=10, le=100_000)
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://alos:andara-alos@127.0.0.1:5433/alos"

    auth_issuer: str = "alos-local"
    auth_audience: str = "alos-platform"
    auth_signing_secret: SecretStr = SecretStr("local-development-only-change-me")
    auth_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    object_storage_provider: Literal["filesystem", "s3"] = "filesystem"
    allow_staging_filesystem_object_storage: bool = False
    object_storage_bucket: str = "alos-documents"
    object_storage_path: Path = Path("./data/objects")
    object_storage_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    object_storage_endpoint_url: str | None = None
    object_storage_region: str = "auto"
    object_storage_access_key_id: SecretStr | None = None
    object_storage_secret_access_key: SecretStr | None = None
    object_storage_force_path_style: bool = False
    object_storage_server_side_encryption: str | None = "AES256"

    llm_provider: LlmProvider = Field(default="disabled", pattern=r"^[a-z][a-z0-9_-]{0,49}$")
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
    llm_max_context_tokens: int = Field(default=12_000, ge=256, le=1_000_000)
    llm_max_data_classification: Literal[
        "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"
    ] = "INTERNAL"
    llm_daily_request_limit: int = Field(default=500, ge=1)
    llm_daily_output_token_limit: int = Field(default=500_000, ge=1_000)
    llm_daily_cost_cap_usd: Decimal = Field(default=Decimal("5.00"), ge=0)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    agentic_max_model_steps: int = Field(default=8, ge=1, le=100)
    agentic_max_tool_calls: int = Field(default=20, ge=0, le=1_000)
    agentic_max_delegation_depth: int = Field(default=0, ge=0, le=16)
    agentic_max_subagents: int = Field(default=0, ge=0, le=100)
    agentic_max_concurrency: int = Field(default=1, ge=1, le=100)
    agentic_max_cost_per_run: Decimal = Field(default=Decimal("1.00"), ge=0)
    genesis_semantic_analysis_enabled: bool = False
    genesis_semantic_max_output_tokens: int = Field(default=1_200, ge=256, le=8_000)
    genesis_conversation_follow_up_enabled: bool = False
    genesis_follow_up_max_output_tokens: int = Field(default=1_200, ge=256, le=8_000)
    source_chunk_max_chars: int = Field(default=1_500, ge=256, le=10_000)
    source_retrieval_max_chars: int = Field(default=10_000, ge=800, le=100_000)
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
        if self.allow_staging_filesystem_object_storage and self.environment != "staging":
            raise ValueError("filesystem object storage override is limited to staging")
        requires_remote_object_storage = self.environment == "production" or (
            self.environment == "staging" and not self.allow_staging_filesystem_object_storage
        )
        if requires_remote_object_storage and self.object_storage_provider != "s3":
            raise ValueError(
                "staging/production requires object storage outside the local filesystem"
            )
        access_key = (
            self.object_storage_access_key_id.get_secret_value().strip()
            if self.object_storage_access_key_id
            else ""
        )
        secret_key = (
            self.object_storage_secret_access_key.get_secret_value().strip()
            if self.object_storage_secret_access_key
            else ""
        )
        if bool(access_key) != bool(secret_key):
            raise ValueError("S3 access key and secret key must be configured together")
        if self.object_storage_provider == "s3" and not self.object_storage_bucket.strip():
            raise ValueError("S3 object storage requires a bucket")
        if (
            self.object_storage_provider == "s3"
            and self.object_storage_endpoint_url
            and not access_key
        ):
            raise ValueError("S3-compatible endpoint requires environment credentials")
        if self.environment in {"staging", "production"} and self.llm_provider not in {
            "disabled",
            "openai",
        }:
            raise ValueError("only registered and approved deployment providers may be enabled")
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
            from alos.model_gateway.pricing import has_openai_pricing

            unknown_models = {model for model in configured_models if not has_openai_pricing(model)}
            if unknown_models:
                raise ValueError(
                    "OpenAI model pricing is not configured for the selected model route"
                )
        if self.environment in {"staging", "production"} and self.llm_store_responses:
            raise ValueError("staging/production must keep provider response storage disabled")
        if (
            self.genesis_semantic_analysis_enabled
            or self.genesis_conversation_follow_up_enabled
        ) and self.llm_provider != "openai":
            raise ValueError("model-backed Genesis features require the OpenAI Model Gateway")
        if (
            self.genesis_semantic_analysis_enabled
            and self.genesis_semantic_max_output_tokens > self.llm_max_output_tokens
        ):
            raise ValueError(
                "Genesis semantic output limit cannot exceed the Model Gateway output limit"
            )
        if (
            self.genesis_conversation_follow_up_enabled
            and self.genesis_follow_up_max_output_tokens > self.llm_max_output_tokens
        ):
            raise ValueError(
                "Genesis follow-up output limit cannot exceed the Model Gateway output limit"
            )
        return self

    def model_for_route(self, route: ModelRoute) -> str:
        """Resolve a Contract model route only from server-side configuration.

        A contract selects a bounded route, never a raw provider model name.
        Empty route overrides intentionally fall back to the configured primary model.
        """
        from alos.model_gateway.routing import resolve_model_route

        return resolve_model_route(
            route,
            default_model=self.llm_model,
            light_model=self.llm_model_light,
            standard_model=self.llm_model_standard,
            critical_model=self.llm_model_critical,
        )

    def estimate_llm_cost_usd(
        self, *, model: str, input_tokens: int, output_tokens: int
    ) -> Decimal:
        """Return a conservative text-token estimate rounded up for budget safety.

        OpenAI routes are validated during Settings construction. Future provider
        adapters must supply an approved pricing policy before deployment.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts cannot be negative")
        if self.llm_provider != "openai":
            return Decimal("0")
        from alos.model_gateway.pricing import estimate_openai_cost_usd

        return estimate_openai_cost_usd(model, input_tokens, output_tokens)


@lru_cache
def get_settings() -> Settings:
    return Settings()
