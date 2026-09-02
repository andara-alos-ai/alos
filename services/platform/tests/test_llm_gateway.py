import json
from pathlib import Path
from typing import Any

import httpx

from alos.llm import DataClassification, LLMGateway, LLMRequest, LLMResultStatus, PromptRegistry
from alos.llm.models import LLMProvider, LLMUsage
from alos.llm.providers import AnthropicProvider, OpenAIProvider, ProviderOutput

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class RecordingProvider:
    provider = LLMProvider.OPENAI

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.received: dict[str, Any] | None = None

    def generate(
        self,
        prompt: object,
        input_data: dict[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput:
        self.received = dict(input_data)
        return ProviderOutput(
            output=self.output,
            request_id="resp_synthetic",
            usage=LLMUsage(input_tokens=10, output_tokens=20),
            latency_ms=5,
            model="synthetic-model",
        )


class FailingProvider:
    provider = LLMProvider.OPENAI

    def generate(
        self,
        prompt: object,
        input_data: dict[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput:
        raise RuntimeError("primary provider unavailable")


def valid_output() -> dict[str, Any]:
    return {
        "summary": "Ringkasan sintetis",
        "findings": [],
        "confidence": 0.8,
        "human_review_required": True,
    }


def test_gateway_redacts_pii_hashes_identity_and_validates_schema() -> None:
    provider = RecordingProvider(valid_output())
    gateway = LLMGateway(PromptRegistry(REPOSITORY_ROOT / "definitions"), provider)

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={"contact": "user@example.com / 081234567890"},
            classification=DataClassification.INTERNAL,
            safety_identifier="real-user@example.com",
        )
    )

    assert result.status == LLMResultStatus.COMPLETED
    assert result.redacted_fields == ("contact",)
    assert provider.received is not None
    assert provider.received["contact"] == "[EMAIL_REDACTED] / [PHONE_REDACTED]"


def test_gateway_records_token_based_cost_estimate() -> None:
    gateway = LLMGateway(
        PromptRegistry(REPOSITORY_ROOT / "definitions"),
        RecordingProvider(valid_output()),
        input_token_cost_usd=0.001,
        output_token_cost_usd=0.002,
    )

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={"value": "synthetic"},
            safety_identifier="user-001",
        )
    )

    assert result.estimated_cost_usd == 0.05


def test_gateway_redacts_pii_in_nested_lists() -> None:
    provider = RecordingProvider(valid_output())
    gateway = LLMGateway(PromptRegistry(REPOSITORY_ROOT / "definitions"), provider)

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={
                "contacts": [
                    {"channel": "reynald@example.com"},
                    ["0812 3456 7890"],
                ]
            },
            classification=DataClassification.INTERNAL,
            safety_identifier="user-001",
        )
    )

    assert result.status == LLMResultStatus.COMPLETED
    assert result.redacted_fields == (
        "contacts[0].channel",
        "contacts[1][0]",
    )
    assert provider.received is not None
    assert provider.received["contacts"] == [
        {"channel": "[EMAIL_REDACTED]"},
        ["[PHONE_REDACTED]"],
    ]


def test_gateway_blocks_restricted_data_before_provider_call() -> None:
    provider = RecordingProvider(valid_output())
    gateway = LLMGateway(PromptRegistry(REPOSITORY_ROOT / "definitions"), provider)

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={"personnel": "restricted"},
            classification=DataClassification.RESTRICTED,
            safety_identifier="user-001",
        )
    )

    assert result.status == LLMResultStatus.BLOCKED
    assert provider.received is None


def test_gateway_fails_closed_on_schema_violation() -> None:
    provider = RecordingProvider({"unexpected": True})
    gateway = LLMGateway(PromptRegistry(REPOSITORY_ROOT / "definitions"), provider)

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={"value": "synthetic"},
            safety_identifier="user-001",
        )
    )

    assert result.status == LLMResultStatus.FAILED
    assert provider.received is not None


def test_gateway_uses_anthropic_fallback_only_after_openai_failure() -> None:
    fallback = RecordingProvider(valid_output())
    fallback.provider = LLMProvider.ANTHROPIC
    gateway = LLMGateway(
        PromptRegistry(REPOSITORY_ROOT / "definitions"),
        FailingProvider(),
        fallback_provider=fallback,
    )

    result = gateway.generate(
        LLMRequest(
            prompt_id="agent.structured-analysis",
            input_data={"value": "synthetic"},
            safety_identifier="user-001",
        )
    )

    assert result.status == LLMResultStatus.COMPLETED
    assert result.provider == LLMProvider.ANTHROPIC
    assert fallback.received == {"value": "synthetic"}
    assert "fallback anthropic used" in result.warnings[0]


def test_openai_provider_uses_responses_structured_output_contract() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["store"] is False
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        assert payload["safety_identifier"] == "hashed-user"
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "model": "gpt-test",
                "output_text": json.dumps(valid_output()),
                "usage": {"input_tokens": 11, "output_tokens": 7},
            },
        )

    provider = OpenAIProvider(
        "test-key",
        "gpt-test",
        transport=httpx.MockTransport(respond),
    )
    prompt = PromptRegistry(REPOSITORY_ROOT / "definitions").get(
        "agent.structured-analysis"
    )

    result = provider.generate(prompt, {"value": "synthetic"}, 100, "hashed-user")

    assert result.output == valid_output()
    assert result.request_id == "resp_test"
    assert result.usage.output_tokens == 7


def test_anthropic_provider_uses_messages_structured_output_contract() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "test-key"
        assert payload["output_config"]["format"]["type"] == "json_schema"
        assert payload["metadata"]["user_id"] == "hashed-user"
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "model": "claude-test",
                "content": [{"type": "text", "text": json.dumps(valid_output())}],
                "usage": {"input_tokens": 9, "output_tokens": 6},
            },
        )

    provider = AnthropicProvider(
        "test-key",
        "claude-test",
        transport=httpx.MockTransport(respond),
    )
    prompt = PromptRegistry(REPOSITORY_ROOT / "definitions").get(
        "agent.structured-analysis"
    )

    result = provider.generate(prompt, {"value": "synthetic"}, 100, "hashed-user")

    assert result.output == valid_output()
    assert result.request_id == "msg_test"
    assert result.usage.output_tokens == 6
