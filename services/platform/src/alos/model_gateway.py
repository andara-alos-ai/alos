"""Provider-neutral Model Gateway contracts for the shared ALOS runtime.

This module intentionally contains no SDK client.  It makes provider policy,
data classification, output limits, and request accounting deterministic and
testable before an external provider is enabled.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from alos.config import Settings

DataClassification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
GatewayProvider = Literal["openai", "anthropic", "gemini", "local", "fake"]

_DATA_CLASSIFICATION_RANK: dict[DataClassification, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}


class ModelGatewayError(RuntimeError):
    """A safe, provider-neutral model gateway failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ModelGatewayPolicyError(ModelGatewayError):
    """The request violates deterministic ALOS policy."""


class ModelGatewayBudgetError(ModelGatewayError):
    """The request exceeds a deterministic request or token budget."""


class ModelGatewayTimeoutError(ModelGatewayError):
    """The selected provider did not return before its timeout policy."""


class ModelUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ModelRequest(BaseModel):
    """A provider-agnostic generation request.

    The application chooses the provider and model through Settings. Callers
    cannot override those routing decisions on an individual request.
    """

    correlation_id: UUID = Field(default_factory=uuid4)
    instructions: str = Field(min_length=1, max_length=50_000)
    input_text: str = Field(min_length=1, max_length=200_000)
    data_classification: DataClassification = "INTERNAL"
    max_output_tokens: int = Field(ge=1, le=128_000)


class ModelResponse(BaseModel):
    provider: GatewayProvider
    model: str = Field(min_length=1, max_length=200)
    output_text: str = Field(min_length=1)
    usage: ModelUsage
    latency_milliseconds: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class ModelGateway(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Return one structured generation result or raise a safe failure."""


class RetryingModelGateway:
    """Retry only transient provider failures; policy and content failures never retry."""

    def __init__(self, delegate: ModelGateway, max_retries: int) -> None:
        if max_retries < 0 or max_retries > 3:
            raise ValueError("max_retries must be between 0 and 3")
        self._delegate = delegate
        self._max_retries = max_retries

    def generate(self, request: ModelRequest) -> ModelResponse:
        for attempt in range(self._max_retries + 1):
            try:
                return self._delegate.generate(request)
            except ModelGatewayError as error:
                if attempt >= self._max_retries or not _is_retryable(error):
                    raise
        raise AssertionError("retry loop must return or raise")


@dataclass
class UsageBudget:
    """In-memory deterministic reservation guard for a single accounting window.

    Persistent daily accounting belongs to the observability module. This guard
    is deliberately in-memory so the runtime policy can be unit-tested before
    persistence and provider SDKs are introduced.
    """

    request_limit: int
    output_token_limit: int
    request_count: int = 0
    output_tokens: int = 0
    _reserved_output_tokens: int = 0

    def reserve(self, requested_output_tokens: int) -> None:
        if self.request_count >= self.request_limit:
            raise ModelGatewayBudgetError("REQUEST_LIMIT", "model request limit reached")
        projected = self.output_tokens + self._reserved_output_tokens + requested_output_tokens
        if projected > self.output_token_limit:
            raise ModelGatewayBudgetError("OUTPUT_TOKEN_LIMIT", "model output token limit reached")
        self.request_count += 1
        self._reserved_output_tokens += requested_output_tokens

    def settle(self, reserved_output_tokens: int, actual_output_tokens: int) -> None:
        self._reserved_output_tokens -= reserved_output_tokens
        self.output_tokens += actual_output_tokens

    def release(self, reserved_output_tokens: int) -> None:
        self._reserved_output_tokens -= reserved_output_tokens


class GuardedModelGateway:
    """Apply deterministic policy before and after a provider call."""

    def __init__(self, delegate: ModelGateway, settings: Settings, budget: UsageBudget) -> None:
        self._delegate = delegate
        self._settings = settings
        self._budget = budget

    def generate(self, request: ModelRequest) -> ModelResponse:
        self._validate_request(request)
        self._budget.reserve(request.max_output_tokens)
        try:
            response = self._delegate.generate(request)
            self._validate_response(request, response)
        except Exception:
            self._budget.release(request.max_output_tokens)
            raise
        self._budget.settle(request.max_output_tokens, response.usage.output_tokens)
        return response

    def _validate_request(self, request: ModelRequest) -> None:
        if self._settings.llm_provider == "disabled":
            raise ModelGatewayPolicyError("PROVIDER_DISABLED", "model gateway is disabled")
        if request.max_output_tokens > self._settings.llm_max_output_tokens:
            raise ModelGatewayPolicyError("OUTPUT_LIMIT", "request exceeds model output policy")
        if (
            _DATA_CLASSIFICATION_RANK[request.data_classification]
            > _DATA_CLASSIFICATION_RANK[self._settings.llm_max_data_classification]
        ):
            raise ModelGatewayPolicyError(
                "DATA_CLASSIFICATION", "request data classification exceeds provider policy"
            )

    def _validate_response(self, request: ModelRequest, response: ModelResponse) -> None:
        if response.provider != self._settings.llm_provider:
            raise ModelGatewayPolicyError(
                "PROVIDER_MISMATCH", "response provider violates route policy"
            )
        if response.usage.output_tokens > request.max_output_tokens:
            raise ModelGatewayPolicyError("OUTPUT_LIMIT", "provider response exceeds request limit")


class FakeModelGateway:
    """A deterministic SDK-free provider used by contract and failure tests."""

    def __init__(self, outcomes: Sequence[ModelResponse | ModelGatewayError] = ()) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, ModelGatewayError):
                raise outcome
            return outcome
        return ModelResponse(
            provider="fake",
            model="fake-model",
            output_text='{"result":"fixture"}',
            usage=ModelUsage(input_tokens=1, output_tokens=1),
            latency_milliseconds=1,
        )


def _is_retryable(error: ModelGatewayError) -> bool:
    return error.code in {"TIMEOUT", "GEMINI_TRANSPORT"} or error.code in {
        "GEMINI_HTTP_500",
        "GEMINI_HTTP_502",
        "GEMINI_HTTP_503",
        "GEMINI_HTTP_504",
    }
