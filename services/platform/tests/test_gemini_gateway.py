import json

import httpx
import pytest

from alos.config import Settings
from alos.gemini_gateway import GeminiModelGateway
from alos.model_gateway import ModelGatewayError, ModelGatewayTimeoutError, ModelRequest


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


def model_request() -> ModelRequest:
    return ModelRequest(
        instructions="Return only a synthetic JSON response.",
        input_text="Synthetic test input.",
        max_output_tokens=50,
    )


def test_gemini_gateway_uses_store_false_and_maps_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "test-only-key"
        assert body["store"] is False
        assert body["generation_config"] == {
            "max_output_tokens": 50,
            "thinking_level": "medium",
        }
        assert body["system_instruction"] == "Return only a synthetic JSON response."
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gemini-3.7-flash",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": '{"result":"fixture"}'}],
                    }
                ],
                "usage": {"total_input_tokens": 12, "total_output_tokens": 9},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = GeminiModelGateway(gemini_settings(), client)

    response = gateway.generate(model_request())

    assert response.provider == "gemini"
    assert response.output_text == '{"result":"fixture"}'
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 9


def test_gemini_gateway_maps_none_to_low_for_gemini_37() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["generation_config"]["thinking_level"] == "low"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gemini-3.7-flash",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": '{"result":"fixture"}'}],
                    }
                ],
                "usage": {"total_input_tokens": 12, "total_output_tokens": 9},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = GeminiModelGateway(gemini_settings(llm_reasoning_effort="none"), client)

    response = gateway.generate(model_request())

    assert response.provider == "gemini"


def test_gemini_gateway_returns_a_safe_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = GeminiModelGateway(gemini_settings(), client)

    with pytest.raises(ModelGatewayTimeoutError, match="timed out"):
        gateway.generate(model_request())


def test_gemini_gateway_redacts_http_failure_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="quota detail must not reach caller")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = GeminiModelGateway(gemini_settings(), client)

    with pytest.raises(ModelGatewayError) as raised:
        gateway.generate(model_request())

    assert raised.value.code == "GEMINI_HTTP_429"
    assert "quota detail" not in str(raised.value)


def test_gemini_gateway_exposes_only_a_safe_non_completed_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "incomplete", "id": "provider-id"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = GeminiModelGateway(gemini_settings(), client)

    with pytest.raises(ModelGatewayError) as raised:
        gateway.generate(model_request())

    assert raised.value.code == "GEMINI_INCOMPLETE"
    assert str(raised.value) == "Gemini interaction status: incomplete"
