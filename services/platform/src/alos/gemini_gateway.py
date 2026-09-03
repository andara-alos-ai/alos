"""Local/test-only Gemini adapter behind the ALOS Model Gateway contract.

The adapter uses Gemini's Interactions API directly so ALOS keeps provider
routing, classification, budget reservation, and output validation in its own
deterministic gateway. It deliberately exposes no Gemini tools and defaults to
``store=false``.
"""

from __future__ import annotations

from decimal import Decimal
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

_DEFAULT_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_THINKING_LEVEL: dict[str, str] = {
    "none": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}
_NON_COMPLETED_STATUSES = {
    "in_progress",
    "requires_action",
    "failed",
    "cancelled",
    "incomplete",
}


class GeminiModelGateway:
    """Adapt a local/test Gemini request to the provider-neutral contract."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.llm_provider != "gemini":
            raise ValueError("GeminiModelGateway requires llm_provider=gemini")
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
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                json={
                    "model": self._settings.llm_model,
                    "input": request.input_text,
                    "system_instruction": request.instructions,
                    "store": False,
                    "generation_config": {
                        "max_output_tokens": request.max_output_tokens,
                        "thinking_level": _gemini_thinking_level(
                            self._settings.llm_model,
                            self._settings.llm_reasoning_effort,
                        ),
                    },
                },
                timeout=self._settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as error:
            raise ModelGatewayTimeoutError("TIMEOUT", "Gemini request timed out") from error
        except httpx.HTTPStatusError as error:
            raise ModelGatewayError(
                f"GEMINI_HTTP_{error.response.status_code}", "Gemini request failed"
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise ModelGatewayError(
                "GEMINI_TRANSPORT", "Gemini request could not be completed"
            ) from error

        if not isinstance(payload, dict):
            raise ModelGatewayError("GEMINI_RESPONSE", "Gemini response must be a JSON object")
        status = payload.get("status")
        if status not in {None, "completed"}:
            safe_status = status if status in _NON_COMPLETED_STATUSES else "unexpected"
            raise ModelGatewayError(
                f"GEMINI_{safe_status.upper()}",
                f"Gemini interaction status: {safe_status}",
            )

        output_text = _extract_output_text(payload)
        if not output_text:
            raise ModelGatewayError("GEMINI_EMPTY_OUTPUT", "Gemini response did not contain text")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        return ModelResponse(
            provider="gemini",
            model=str(payload.get("model") or self._settings.llm_model),
            output_text=output_text,
            usage=ModelUsage(
                input_tokens=_token_count(usage, "total_input_tokens"),
                output_tokens=_token_count(usage, "total_output_tokens"),
            ),
            latency_milliseconds=round((perf_counter() - started_at) * 1_000),
            # Provider pricing is intentionally not guessed. Persistent cost accounting
            # is added when the observability ledger is wired into the runtime.
            estimated_cost_usd=Decimal("0"),
        )

    @property
    def _api_key(self) -> str:
        assert self._settings.llm_api_key is not None
        return self._settings.llm_api_key.get_secret_value()

    @property
    def _endpoint(self) -> str:
        return (self._settings.llm_base_url or _DEFAULT_INTERACTIONS_URL).rstrip("/")


def _extract_output_text(payload: dict[str, Any]) -> str:
    text_parts: list[str] = []
    for step in payload.get("steps", []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for content in step.get("content", []):
            if isinstance(content, dict) and content.get("type") == "text":
                text = content.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
    return "".join(text_parts)


def _gemini_thinking_level(model: str, effort: str) -> str:
    """Map ALOS policy to the selected Gemini model's supported level.

    Gemini 3.7 Flash does not accept ``minimal``. ``low`` is its least-cost,
    lowest-latency supported thinking level, so it is the safe local mapping
    for the provider-neutral ALOS ``none`` policy.
    """
    level = _THINKING_LEVEL[effort]
    normalized_model = model.removeprefix("models/").casefold()
    if level == "minimal" and normalized_model.startswith("gemini-3.7"):
        return "low"
    return level


def _token_count(usage: dict[str, Any], field: str) -> int:
    value = usage.get(field, 0)
    return value if isinstance(value, int) and value >= 0 else 0
