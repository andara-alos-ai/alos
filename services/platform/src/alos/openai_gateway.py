"""OpenAI Responses adapter behind the shared ALOS Model Gateway.

This adapter owns only the provider HTTP translation. ALOS continues to own
tool execution, permission checks, budgets, audit records, and lifecycle
decisions before a request reaches OpenAI.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from alos.config import Settings
from alos.model_gateway import (
    ModelGatewayError,
    ModelGatewayTimeoutError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)

_DEFAULT_RESPONSES_BASE_URL = "https://api.openai.com/v1"
_NON_COMPLETED_STATUSES = {
    "failed",
    "in_progress",
    "cancelled",
    "queued",
    "incomplete",
}


class OpenAIModelGateway:
    """Translate a bounded ALOS request to one stateless OpenAI Response."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.llm_provider != "openai":
            raise ValueError("OpenAIModelGateway requires llm_provider=openai")
        self._settings = settings
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, request: ModelRequest) -> ModelResponse:
        started_at = perf_counter()
        try:
            response = self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-Client-Request-Id": str(request.correlation_id),
                },
                json={
                    "model": request.model or self._settings.llm_model,
                    "instructions": request.instructions,
                    "input": request.input_text,
                    "max_output_tokens": request.max_output_tokens,
                    "reasoning": {"effort": self._settings.llm_reasoning_effort},
                    "text": {"verbosity": "low"},
                    "metadata": {"alos_correlation_id": str(request.correlation_id)},
                    "store": False,
                },
                timeout=self._settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as error:
            raise ModelGatewayTimeoutError("TIMEOUT", "OpenAI request timed out") from error
        except httpx.HTTPStatusError as error:
            raise ModelGatewayError(
                f"OPENAI_HTTP_{error.response.status_code}", "OpenAI request failed"
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise ModelGatewayError(
                "OPENAI_TRANSPORT", "OpenAI request could not be completed"
            ) from error

        if not isinstance(payload, dict):
            raise ModelGatewayError("OPENAI_RESPONSE", "OpenAI response must be a JSON object")
        status = payload.get("status")
        if status != "completed":
            safe_status = status if status in _NON_COMPLETED_STATUSES else "unexpected"
            raise ModelGatewayError(
                f"OPENAI_{str(safe_status).upper()}",
                f"OpenAI response status: {safe_status}",
            )

        output_text = _extract_output_text(payload)
        if not output_text:
            raise ModelGatewayError("OPENAI_EMPTY_OUTPUT", "OpenAI response did not contain text")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        requested_model = request.model or self._settings.llm_model
        response_model = payload.get("model")
        if response_model is not None and response_model != requested_model:
            raise ModelGatewayError(
                "OPENAI_MODEL_MISMATCH", "OpenAI response model violates route policy"
            )
        model_usage = ModelUsage(
            input_tokens=_token_count(usage, "input_tokens"),
            output_tokens=_token_count(usage, "output_tokens"),
        )
        return ModelResponse(
            provider="openai",
            model=requested_model,
            output_text=output_text,
            usage=model_usage,
            latency_milliseconds=round((perf_counter() - started_at) * 1_000),
            estimated_cost_usd=self._settings.estimate_llm_cost_usd(
                model=requested_model,
                input_tokens=model_usage.input_tokens,
                output_tokens=model_usage.output_tokens,
            ),
        )

    @property
    def _api_key(self) -> str:
        assert self._settings.llm_api_key is not None
        return self._settings.llm_api_key.get_secret_value()

    @property
    def _endpoint(self) -> str:
        base_url = self._settings.llm_base_url or _DEFAULT_RESPONSES_BASE_URL
        return f"{base_url.rstrip('/')}/responses"


def _extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    text_parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            text = content.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
    return "".join(text_parts)


def _token_count(usage: dict[str, Any], field: str) -> int:
    value = usage.get(field, 0)
    return value if isinstance(value, int) and value >= 0 else 0
