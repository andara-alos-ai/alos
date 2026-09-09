from decimal import Decimal

import pytest

from alos.config import Settings
from alos.gemini_smoke import execute_local_smoke
from alos.model_gateway import FakeModelGateway, ModelGatewayPolicyError, ModelResponse, ModelUsage


def gemini_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "local",
        "llm_provider": "gemini",
        "llm_api_key": "test-only-key",
        "llm_model": "gemini-3.7-flash",
        "llm_max_output_tokens": 256,
    }
    values.update(overrides)
    return Settings(**values)


def test_local_smoke_is_limited_to_one_public_request() -> None:
    fake = FakeModelGateway(
        [
            ModelResponse(
                provider="gemini",
                model="gemini-3.7-flash",
                output_text='{"status":"gemini_smoke_ok"}',
                usage=ModelUsage(input_tokens=10, output_tokens=8),
                latency_milliseconds=1,
                estimated_cost_usd=Decimal("0"),
            )
        ]
    )

    response = execute_local_smoke(gemini_settings(), fake)

    assert response.provider == "gemini"
    assert len(fake.requests) == 1
    assert fake.requests[0].data_classification == "PUBLIC"
    assert fake.requests[0].max_output_tokens == 256


def test_local_smoke_rejects_a_non_gemini_provider() -> None:
    with pytest.raises(ModelGatewayPolicyError, match="requires llm_provider=gemini"):
        execute_local_smoke(
            gemini_settings(llm_provider="openai"),
            FakeModelGateway(),
        )
