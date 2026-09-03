"""One bounded OpenAI Responses connectivity check for local or staging ALOS."""

from __future__ import annotations

import json

from alos.config import Settings
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGateway,
    ModelGatewayPolicyError,
    ModelRequest,
    ModelResponse,
    UsageBudget,
)
from alos.openai_gateway import OpenAIModelGateway

_SMOKE_MAX_OUTPUT_TOKENS = 512
_SMOKE_PROMPT = "Return exactly this JSON: {\"status\":\"openai_smoke_ok\"}."


def execute_openai_smoke(settings: Settings, delegate: ModelGateway) -> ModelResponse:
    """Run one small, public, no-tool OpenAI request through ALOS guardrails."""
    if settings.environment not in {"local", "test", "staging"}:
        raise ModelGatewayPolicyError("STAGING_ONLY", "OpenAI smoke is limited to local/staging")
    if settings.llm_provider != "openai":
        raise ModelGatewayPolicyError("PROVIDER", "OpenAI smoke requires the OpenAI Model Gateway")

    output_limit = min(_SMOKE_MAX_OUTPUT_TOKENS, settings.llm_max_output_tokens)
    gateway = GuardedModelGateway(
        delegate,
        settings,
        UsageBudget(request_limit=1, output_token_limit=output_limit),
    )
    return gateway.generate(
        ModelRequest(
            model=settings.model_for_route("light"),
            instructions=(
                "You are an ALOS connectivity check. Do not use tools or access external data."
            ),
            input_text=_SMOKE_PROMPT,
            data_classification="PUBLIC",
            max_output_tokens=output_limit,
        )
    )


def main() -> None:
    settings = Settings()
    delegate = OpenAIModelGateway(settings)
    try:
        response = execute_openai_smoke(settings, delegate)
    finally:
        delegate.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "provider": response.provider,
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_milliseconds": response.latency_milliseconds,
                "output_preview": response.output_text[:200],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
