from decimal import Decimal

import pytest

from alos.config import Settings
from alos.model_gateway import (
    FakeModelGateway,
    GuardedModelGateway,
    ModelGatewayBudgetError,
    ModelGatewayPolicyError,
    ModelGatewayTimeoutError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    RetryingModelGateway,
    UsageBudget,
)


def enabled_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "auth_signing_secret": "a" * 32,
        "llm_provider": "openai",
        "llm_api_key": "test-only-key",
        "llm_model": "test-model",
        "llm_max_output_tokens": 256,
        "llm_daily_request_limit": 2,
        "llm_daily_output_token_limit": 1_000,
        "llm_max_data_classification": "INTERNAL",
    }
    values.update(overrides)
    return Settings(**values)


def response(output_tokens: int = 25) -> ModelResponse:
    return ModelResponse(
        provider="openai",
        model="test-model",
        output_text='{"status":"ok"}',
        usage=ModelUsage(input_tokens=12, output_tokens=output_tokens),
        latency_milliseconds=42,
        estimated_cost_usd=Decimal("0.001"),
    )


def request(**overrides: object) -> ModelRequest:
    values: dict[str, object] = {
        "instructions": "Return a synthetic JSON response.",
        "input_text": "Synthetic test input.",
        "max_output_tokens": 50,
    }
    values.update(overrides)
    return ModelRequest(**values)


def test_guarded_gateway_records_usage_after_a_valid_response() -> None:
    fake = FakeModelGateway([response()])
    budget = UsageBudget(request_limit=2, output_token_limit=100)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)
    model_request = request()

    assert gateway.generate(model_request).model == "test-model"
    assert fake.requests == [model_request]
    assert budget.request_count == 1
    assert budget.output_tokens == 25


def test_gateway_rejects_an_output_request_above_policy_before_provider_call() -> None:
    fake = FakeModelGateway([response()])
    budget = UsageBudget(request_limit=2, output_token_limit=100)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)

    with pytest.raises(ModelGatewayPolicyError, match="output policy"):
        gateway.generate(request(max_output_tokens=257))

    assert fake.requests == []
    assert budget.request_count == 0


def test_gateway_rejects_restricted_data_before_provider_call() -> None:
    fake = FakeModelGateway([response()])
    budget = UsageBudget(request_limit=2, output_token_limit=100)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)

    with pytest.raises(ModelGatewayPolicyError, match="classification"):
        gateway.generate(request(data_classification="RESTRICTED"))

    assert fake.requests == []


def test_gateway_reserves_a_conservative_daily_output_budget_before_provider_call() -> None:
    fake = FakeModelGateway([response()])
    budget = UsageBudget(request_limit=2, output_token_limit=90)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)

    with pytest.raises(ModelGatewayBudgetError, match="output token limit"):
        gateway.generate(request(max_output_tokens=91))

    assert fake.requests == []
    assert budget.request_count == 0


def test_gateway_releases_reserved_tokens_after_provider_timeout() -> None:
    fake = FakeModelGateway(
        [
            ModelGatewayTimeoutError("TIMEOUT", "provider timed out"),
            response(),
        ]
    )
    budget = UsageBudget(request_limit=2, output_token_limit=100)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)

    with pytest.raises(ModelGatewayTimeoutError, match="timed out"):
        gateway.generate(request())
    assert budget.output_tokens == 0

    assert gateway.generate(request()).usage.output_tokens == 25
    assert budget.request_count == 2
    assert budget.output_tokens == 25


def test_gateway_rejects_a_provider_response_that_exceeds_reserved_output_limit() -> None:
    fake = FakeModelGateway([response(output_tokens=51)])
    budget = UsageBudget(request_limit=2, output_token_limit=100)
    gateway = GuardedModelGateway(fake, enabled_settings(), budget)

    with pytest.raises(ModelGatewayPolicyError, match="exceeds request limit"):
        gateway.generate(request(max_output_tokens=50))

    assert budget.output_tokens == 0


def test_retrying_gateway_retries_only_transient_provider_errors() -> None:
    fake = FakeModelGateway(
        [
            ModelGatewayTimeoutError("TIMEOUT", "provider timed out"),
            response(),
        ]
    )

    result = RetryingModelGateway(fake, max_retries=1).generate(request())

    assert result.model == "test-model"
    assert len(fake.requests) == 2
