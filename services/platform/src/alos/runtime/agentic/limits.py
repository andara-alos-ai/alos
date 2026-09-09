"""Deterministic limits shared by every agentic engine implementation."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionLimits(BaseModel):
    """Per-run and daily ceilings that an engine must never exceed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_steps: int = Field(default=8, ge=1, le=1_000)
    max_tool_calls: int = Field(default=20, ge=0, le=10_000)
    max_elapsed_seconds: float = Field(default=120.0, gt=0, le=86_400)
    max_retries: int = Field(default=1, ge=0, le=10)
    max_delegation_depth: int = Field(default=0, ge=0, le=32)
    max_subagents: int = Field(default=0, ge=0, le=1_000)
    max_concurrency: int = Field(default=1, ge=1, le=1_000)
    max_input_tokens: int = Field(default=12_000, ge=1, le=10_000_000)
    max_output_tokens: int = Field(default=3_000, ge=1, le=10_000_000)
    max_total_tokens: int = Field(default=15_000, ge=1, le=20_000_000)
    max_cost_per_run: Decimal = Field(default=Decimal("1.00"), ge=0)
    daily_agent_cost_limit: Decimal = Field(default=Decimal("5.00"), ge=0)

    @model_validator(mode="after")
    def validate_token_envelope(self) -> "ExecutionLimits":
        if self.max_input_tokens + self.max_output_tokens > self.max_total_tokens:
            raise ValueError(
                "max_total_tokens must cover max_input_tokens plus max_output_tokens"
            )
        if self.max_cost_per_run > self.daily_agent_cost_limit:
            raise ValueError("max_cost_per_run cannot exceed daily_agent_cost_limit")
        return self
