"""Deterministic policy and in-process reservation guards."""

from dataclasses import dataclass

from alos.config import Settings
from alos.model_gateway.gateway import (
    ModelGateway,
    ModelGatewayBudgetError,
    ModelGatewayPolicyError,
)
from alos.model_gateway.models import DataClassification, ModelRequest, ModelResponse

_CLASSIFICATION_RANK: dict[DataClassification, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}


@dataclass
class UsageBudget:
    """Reserve a bounded amount before dispatching one provider request."""

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
    """Apply ALOS policy before and after a provider call."""

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
            _CLASSIFICATION_RANK[request.data_classification]
            > _CLASSIFICATION_RANK[self._settings.llm_max_data_classification]
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
