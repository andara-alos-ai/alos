import json
import time
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from alos.llm.models import LLMProvider, LLMUsage
from alos.llm.prompts import PromptDefinition


class ProviderOutput:
    def __init__(
        self,
        *,
        output: dict[str, Any],
        request_id: str | None,
        usage: LLMUsage,
        latency_ms: int,
        model: str,
    ) -> None:
        self.output = output
        self.request_id = request_id
        self.usage = usage
        self.latency_ms = latency_ms
        self.model = model


class LLMProviderAdapter(Protocol):
    provider: LLMProvider

    def generate(
        self,
        prompt: PromptDefinition,
        input_data: Mapping[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput: ...


class DisabledProvider:
    provider = LLMProvider.DISABLED

    def generate(
        self,
        prompt: PromptDefinition,
        input_data: Mapping[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput:
        raise RuntimeError("LLM provider dinonaktifkan")


class OpenAIProvider:
    provider = LLMProvider.OPENAI

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def generate(
        self,
        prompt: PromptDefinition,
        input_data: Mapping[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput:
        started = time.monotonic()
        response = self._client.post(
            "/responses",
            json={
                "model": self._model,
                "instructions": prompt.instructions,
                "input": json.dumps(input_data, ensure_ascii=False),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": prompt.prompt_id.replace(".", "_"),
                        "schema": prompt.output_schema,
                        "strict": True,
                    }
                },
                "max_output_tokens": max_output_tokens,
                "safety_identifier": safety_identifier,
                "store": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("output_text") or self._extract_output_text(payload)
        output = json.loads(raw)
        usage = payload.get("usage") or {}
        return ProviderOutput(
            output=output,
            request_id=payload.get("id"),
            usage=LLMUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=str(payload.get("model") or self._model),
        )

    @staticmethod
    def _extract_output_text(payload: Mapping[str, Any]) -> str:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise ValueError("OpenAI response tidak memuat output_text")


class AnthropicProvider:
    provider = LLMProvider.ANTHROPIC

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    def generate(
        self,
        prompt: PromptDefinition,
        input_data: Mapping[str, Any],
        max_output_tokens: int,
        safety_identifier: str,
    ) -> ProviderOutput:
        started = time.monotonic()
        response = self._client.post(
            "/messages",
            json={
                "model": self._model,
                "max_tokens": max_output_tokens,
                "system": prompt.instructions,
                "messages": [
                    {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}
                ],
                "output_config": {
                    "format": {"type": "json_schema", "schema": prompt.output_schema}
                },
                "metadata": {"user_id": safety_identifier},
            },
        )
        response.raise_for_status()
        payload = response.json()
        raw = next(
            (
                block.get("text")
                for block in payload.get("content", [])
                if block.get("type") == "text" and isinstance(block.get("text"), str)
            ),
            None,
        )
        if raw is None:
            raise ValueError("Anthropic response tidak memuat text content")
        usage = payload.get("usage") or {}
        return ProviderOutput(
            output=json.loads(raw),
            request_id=payload.get("id"),
            usage=LLMUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=str(payload.get("model") or self._model),
        )
