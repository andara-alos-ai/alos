"""Provider-neutral request, response, and usage models."""

from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

DataClassification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
ModelRoute = Literal["light", "standard", "critical"]
GatewayProvider = str


class ModelUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ModelRequest(BaseModel):
    """A provider-neutral request after server-side route resolution."""

    correlation_id: UUID = Field(default_factory=uuid4)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=50_000)
    input_text: str = Field(min_length=1, max_length=200_000)
    data_classification: DataClassification = "INTERNAL"
    max_output_tokens: int = Field(ge=1, le=128_000)


class ModelResponse(BaseModel):
    provider: GatewayProvider = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    output_text: str = Field(min_length=1)
    usage: ModelUsage
    latency_milliseconds: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
