import hashlib
import re
import threading
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import httpx

from alos.llm.models import (
    DataClassification,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMResultStatus,
)
from alos.llm.prompts import PromptRegistry
from alos.llm.providers import LLMProviderAdapter

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?62|0)\d[\d -]{7,15}\d(?!\d)")


class LLMGatewayError(RuntimeError):
    pass


class LLMGateway:
    """Provider-neutral boundary enforcing policy before any external AI call."""

    def __init__(
        self,
        prompts: PromptRegistry,
        provider: LLMProviderAdapter,
        *,
        max_classification: DataClassification = DataClassification.INTERNAL,
        daily_request_limit: int = 500,
        daily_output_token_limit: int = 500_000,
        max_attempts: int = 2,
    ) -> None:
        self._prompts = prompts
        self._provider = provider
        self._max_classification = max_classification
        self._daily_request_limit = daily_request_limit
        self._daily_output_token_limit = daily_output_token_limit
        self._max_attempts = max(1, min(max_attempts, 3))
        self._lock = threading.Lock()
        self._budget_date = date.today()
        self._requests = 0
        self._output_tokens = 0
        self._reserved_output_tokens = 0

    def generate(self, request: LLMRequest) -> LLMResult:
        prompt = self._prompts.get(request.prompt_id, request.prompt_version)
        if self._provider.provider == LLMProvider.DISABLED:
            return self._non_execution_result(
                request,
                prompt.prompt_digest,
                prompt.version,
                LLMResultStatus.DISABLED,
                "LLM provider dinonaktifkan; hasil memerlukan pemeriksaan manusia.",
            )
        if request.classification > self._max_classification:
            return self._non_execution_result(
                request,
                prompt.prompt_digest,
                prompt.version,
                LLMResultStatus.BLOCKED,
                "Klasifikasi data melampaui kebijakan provider eksternal.",
            )
        if not self._reserve_budget(request.max_output_tokens):
            return self._non_execution_result(
                request,
                prompt.prompt_digest,
                prompt.version,
                LLMResultStatus.BLOCKED,
                "Batas penggunaan LLM harian tercapai.",
            )
        redacted, redacted_fields = self._redact_mapping(request.input_data)
        safety_hash = hashlib.sha256(request.safety_identifier.encode("utf-8")).hexdigest()[:64]
        last_error: Exception | None = None
        for _attempt in range(1, self._max_attempts + 1):
            try:
                provider_result = self._provider.generate(
                    prompt, redacted, request.max_output_tokens, safety_hash
                )
                self._validate_json_schema(provider_result.output, prompt.output_schema)
                self._record_usage(
                    request.max_output_tokens, provider_result.usage.output_tokens
                )
                return LLMResult(
                    status=LLMResultStatus.COMPLETED,
                    output=provider_result.output,
                    provider=self._provider.provider,
                    model=provider_result.model,
                    prompt_id=prompt.prompt_id,
                    prompt_version=prompt.version,
                    prompt_digest=prompt.prompt_digest,
                    provider_request_id=provider_result.request_id,
                    usage=provider_result.usage,
                    latency_ms=provider_result.latency_ms,
                    redacted_fields=redacted_fields,
                )
            except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
                last_error = exc
        if last_error is None:
            last_error = RuntimeError("LLM gagal tanpa detail error")
        self._release_reservation(request.max_output_tokens)
        return LLMResult(
            status=LLMResultStatus.FAILED,
            provider=self._provider.provider,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_digest=prompt.prompt_digest,
            redacted_fields=redacted_fields,
            warnings=(
                f"Panggilan LLM gagal aman setelah {self._max_attempts} percobaan: "
                f"{type(last_error).__name__}",
            ),
        )

    def _reserve_budget(self, requested_tokens: int) -> bool:
        with self._lock:
            today = datetime.now(UTC).date()
            if today != self._budget_date:
                self._budget_date = today
                self._requests = 0
                self._output_tokens = 0
                self._reserved_output_tokens = 0
            if self._requests >= self._daily_request_limit:
                return False
            if (
                self._output_tokens + self._reserved_output_tokens + requested_tokens
                > self._daily_output_token_limit
            ):
                return False
            self._requests += 1
            self._reserved_output_tokens += requested_tokens
            return True

    def _record_usage(self, reserved_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self._reserved_output_tokens = max(
                0, self._reserved_output_tokens - reserved_tokens
            )
            self._output_tokens += output_tokens

    def _release_reservation(self, reserved_tokens: int) -> None:
        with self._lock:
            self._reserved_output_tokens = max(
                0, self._reserved_output_tokens - reserved_tokens
            )

    @classmethod
    def _redact_mapping(
        cls, source: Mapping[str, Any], prefix: str = ""
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        result: dict[str, Any] = {}
        redacted: list[str] = []
        for key, value in source.items():
            path = f"{prefix}.{key}" if prefix else key
            masked, nested_fields = cls._redact_value(value, path)
            result[key] = masked
            redacted.extend(nested_fields)
        return result, tuple(sorted(set(redacted)))

    @classmethod
    def _redact_value(cls, value: Any, path: str) -> tuple[Any, list[str]]:
        if isinstance(value, Mapping):
            nested, nested_fields = cls._redact_mapping(value, path)
            return nested, list(nested_fields)
        if isinstance(value, list):
            masked_items: list[Any] = []
            redacted: list[str] = []
            for index, item in enumerate(value):
                masked, list_fields = cls._redact_value(item, f"{path}[{index}]")
                masked_items.append(masked)
                redacted.extend(list_fields)
            return masked_items, redacted
        if isinstance(value, str):
            masked = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", value)
            masked = PHONE_PATTERN.sub("[PHONE_REDACTED]", masked)
            return masked, [path] if masked != value else []
        return value, []

    def _non_execution_result(
        self,
        request: LLMRequest,
        prompt_digest: str,
        prompt_version: str,
        status: LLMResultStatus,
        warning: str,
    ) -> LLMResult:
        return LLMResult(
            status=status,
            provider=self._provider.provider,
            prompt_id=request.prompt_id,
            prompt_version=prompt_version,
            prompt_digest=prompt_digest,
            warnings=(warning,),
        )

    @classmethod
    def _validate_json_schema(
        cls, value: Any, schema: Mapping[str, Any], path: str = "$"
    ) -> None:
        expected = schema.get("type")
        type_matches = {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "number": isinstance(value, int | float) and not isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }
        if isinstance(expected, str) and not type_matches.get(expected, False):
            raise ValueError(f"Output LLM tidak sesuai schema pada {path}: {expected}")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"Output LLM di luar enum pada {path}")
        if expected == "object":
            if not isinstance(value, dict):
                raise ValueError(f"Output LLM bukan object pada {path}")
            required = set(schema.get("required", []))
            missing = required - set(value)
            if missing:
                raise ValueError(f"Output LLM kehilangan field pada {path}: {sorted(missing)}")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                unexpected = set(value) - set(properties)
                if unexpected:
                    raise ValueError(
                        f"Output LLM memiliki field tidak diizinkan pada {path}: "
                        f"{sorted(unexpected)}"
                    )
            for key, item in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, Mapping):
                    cls._validate_json_schema(item, child_schema, f"{path}.{key}")
        elif expected == "array":
            if not isinstance(value, list):
                raise ValueError(f"Output LLM bukan array pada {path}")
            item_schema = schema.get("items")
            if isinstance(item_schema, Mapping):
                for index, item in enumerate(value):
                    cls._validate_json_schema(item, item_schema, f"{path}[{index}]")
