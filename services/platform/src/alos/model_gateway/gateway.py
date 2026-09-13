"""Core ModelGateway protocol and provider-neutral failures."""

from collections.abc import Sequence
from typing import Protocol

from alos.model_gateway.models import ModelRequest, ModelResponse, ModelUsage


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


class ModelGateway(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Return one structured generation result or raise a safe failure."""


class RetryingModelGateway:
    """Retry only explicitly transient provider failures."""

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


class FakeModelGateway:
    """Deterministic SDK-free test double for gateway contract tests."""

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
    if error.code == "TIMEOUT" or error.code.endswith("_TRANSPORT"):
        return True
    return any(error.code.endswith(f"_HTTP_{status}") for status in (500, 502, 503, 504))
