import json
from decimal import Decimal

import httpx
import pytest

from alos.config import Settings
from alos.model_gateway import ModelGatewayError, ModelGatewayTimeoutError, ModelRequest
from alos.model_gateway_factory import create_model_gateway
from alos.openai_gateway import OpenAIModelGateway


def openai_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "staging",
        "auth_signing_secret": "test-only-signing-secret-that-is-long-enough",
        "llm_provider": "openai",
        "llm_api_key": "test-only-key",
        "llm_model": "gpt-5.6-luna",
        "llm_model_light": "gpt-5.6-luna",
        "llm_model_standard": "gpt-5.6-terra",
        "llm_model_critical": "gpt-5.6-sol",
        "llm_max_output_tokens": 512,
    }
    values.update(overrides)
    return Settings(**values)


def model_request() -> ModelRequest:
    return ModelRequest(
        model="gpt-5.6-luna",
        instructions="Return only a synthetic JSON response.",
        input_text="Synthetic test input.",
        max_output_tokens=50,
    )


def test_openai_gateway_uses_stateless_responses_and_maps_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer test-only-key"
        assert request.headers["x-client-request-id"]
        assert body == {
            "model": "gpt-5.6-luna",
            "instructions": "Return only a synthetic JSON response.",
            "input": "Synthetic test input.",
            "max_output_tokens": 50,
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "low"},
            "metadata": {"alos_correlation_id": request.headers["x-client-request-id"]},
            "store": False,
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gpt-5.6-luna",
                "output_text": '{"result":"fixture"}',
                "usage": {"input_tokens": 12, "output_tokens": 9},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = OpenAIModelGateway(openai_settings(), client)

    response = gateway.generate(model_request())

    assert response.provider == "openai"
    assert response.model == "gpt-5.6-luna"
    assert response.output_text == '{"result":"fixture"}'
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 9
    assert response.estimated_cost_usd == Decimal("0.000014")


def test_openai_gateway_extracts_output_text_from_message_content() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"result":"fixture"}'}],
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = OpenAIModelGateway(openai_settings(), client).generate(model_request())

    assert response.output_text == '{"result":"fixture"}'


def test_openai_gateway_returns_a_safe_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = OpenAIModelGateway(openai_settings(), client)

    with pytest.raises(ModelGatewayTimeoutError, match="timed out"):
        gateway.generate(model_request())


def test_openai_gateway_redacts_http_failure_details() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="quota detail must not reach caller")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = OpenAIModelGateway(openai_settings(), client)

    with pytest.raises(ModelGatewayError) as raised:
        gateway.generate(model_request())

    assert raised.value.code == "OPENAI_HTTP_429"
    assert "quota detail" not in str(raised.value)


def test_openai_gateway_exposes_only_a_safe_non_completed_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "incomplete", "id": "provider-id"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = OpenAIModelGateway(openai_settings(), client)

    with pytest.raises(ModelGatewayError) as raised:
        gateway.generate(model_request())

    assert raised.value.code == "OPENAI_INCOMPLETE"
    assert str(raised.value) == "OpenAI response status: incomplete"


def test_model_routes_resolve_only_from_server_configuration() -> None:
    settings = openai_settings()

    assert settings.model_for_route("light") == "gpt-5.6-luna"
    assert settings.model_for_route("standard") == "gpt-5.6-terra"
    assert settings.model_for_route("critical") == "gpt-5.6-sol"


def test_factory_selects_openai_gateway() -> None:
    gateway, close = create_model_gateway(openai_settings())
    try:
        assert isinstance(gateway, OpenAIModelGateway)
    finally:
        close()
