"""Explicit one-request Gemini connectivity smoke test for local ALOS work."""

from __future__ import annotations

import json

from alos.config import Settings, get_settings
from alos.gemini_gateway import GeminiModelGateway
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGateway,
    ModelGatewayPolicyError,
    ModelRequest,
    ModelResponse,
    UsageBudget,
)

_SMOKE_MAX_OUTPUT_TOKENS = 256
_SMOKE_PROMPT = "Return exactly this JSON: {\"status\":\"gemini_smoke_ok\"}."


def execute_local_smoke(settings: Settings, delegate: ModelGateway) -> ModelResponse:
    """Run one bounded, public, no-tool request through deterministic guardrails."""
    if settings.environment not in {"local", "test"}:
        raise ModelGatewayPolicyError("LOCAL_ONLY", "Gemini smoke is limited to local/test")
    if settings.llm_provider != "gemini":
        raise ModelGatewayPolicyError("PROVIDER", "Gemini smoke requires llm_provider=gemini")

    output_limit = min(_SMOKE_MAX_OUTPUT_TOKENS, settings.llm_max_output_tokens)
    gateway = GuardedModelGateway(
        delegate,
        settings,
        UsageBudget(request_limit=1, output_token_limit=output_limit),
    )
    return gateway.generate(
        ModelRequest(
            instructions=(
                "You are an ALOS connectivity check. Do not use tools or access external data."
            ),
            input_text=_SMOKE_PROMPT,
            data_classification="PUBLIC",
            max_output_tokens=output_limit,
        )
    )


def main() -> None:
    settings = get_settings()
    delegate = GeminiModelGateway(settings)
    try:
        response = execute_local_smoke(settings, delegate)
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
