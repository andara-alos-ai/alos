"""Runtime policy, validation, and deterministic request/response helpers."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from math import ceil
from typing import Any, Literal, cast

from alos.agents.registry import AgentContract
from alos.config import Settings
from alos.model_gateway import DataClassification
from alos.runtime.agentic import ExecutionLimits
from alos.runtime.errors import AgentRuntimeBlocked, InputSchemaError, OutputSchemaError
from alos.runtime.models import AgentRunRequest


def _resolve_model_policy(
    contract: AgentContract, settings: Settings, maximum_output_tokens: int
) -> tuple[str, int]:
    """Resolve the bounded, server-owned model selection used for reservation and execution."""
    configured_provider = contract.model_policy.get("provider")
    if configured_provider not in {None, settings.llm_provider}:
        raise AgentRuntimeBlocked("contract model provider does not match Model Gateway policy")
    configured_limit = contract.model_policy.get("max_output_tokens", maximum_output_tokens)
    if isinstance(configured_limit, bool) or not isinstance(configured_limit, int):
        raise AgentRuntimeBlocked("contract output token policy is invalid")
    output_limit = min(configured_limit, maximum_output_tokens)
    if output_limit < 1:
        raise AgentRuntimeBlocked("contract output token policy is invalid")
    model_route = contract.model_policy.get("model_route", "standard")
    if model_route not in {"light", "standard", "critical"}:
        raise AgentRuntimeBlocked("contract model route is invalid")
    route = cast(Literal["light", "standard", "critical"], model_route)
    return settings.model_for_route(route), output_limit


def _uses_agentic_engine(contract: AgentContract) -> bool:
    return contract.model_policy.get("execution_engine") == "PYDANTICAI"


def _contract_classification(contract: AgentContract) -> DataClassification:
    value = contract.model_policy.get("data_classification", "INTERNAL")
    if value not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise AgentRuntimeBlocked("contract data classification is invalid")
    return cast(DataClassification, value)


def _resolve_agentic_limits(
    contract: AgentContract,
    settings: Settings,
    *,
    output_limit: int,
) -> ExecutionLimits:
    policy = contract.model_policy
    maximum_input = max(1, settings.llm_max_context_tokens - output_limit)
    max_cost = min(
        Decimal(str(policy.get("max_cost_per_run", settings.agentic_max_cost_per_run))),
        settings.agentic_max_cost_per_run,
        settings.llm_daily_cost_cap_usd,
    )
    return ExecutionLimits(
        max_model_steps=min(
            _policy_int(policy, "max_model_steps", settings.agentic_max_model_steps),
            settings.agentic_max_model_steps,
        ),
        max_tool_calls=min(
            _policy_int(policy, "max_tool_calls", settings.agentic_max_tool_calls),
            settings.agentic_max_tool_calls,
        ),
        max_elapsed_seconds=min(
            float(policy.get("max_elapsed_seconds", contract.timeout_seconds)),
            float(contract.timeout_seconds),
        ),
        max_retries=min(
            _policy_int(policy, "max_retries", settings.llm_max_retries),
            settings.llm_max_retries,
        ),
        max_delegation_depth=min(
            _policy_int(
                policy,
                "max_delegation_depth",
                settings.agentic_max_delegation_depth,
            ),
            settings.agentic_max_delegation_depth,
        ),
        max_subagents=min(
            _policy_int(policy, "max_subagents", settings.agentic_max_subagents),
            settings.agentic_max_subagents,
        ),
        max_concurrency=min(
            _policy_int(policy, "max_concurrency", settings.agentic_max_concurrency),
            settings.agentic_max_concurrency,
        ),
        max_input_tokens=maximum_input,
        max_output_tokens=output_limit,
        max_total_tokens=settings.llm_max_context_tokens,
        max_cost_per_run=max_cost,
        daily_agent_cost_limit=settings.llm_daily_cost_cap_usd,
    )


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    value = policy.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentRuntimeBlocked(f"contract {key} policy is invalid")
    return cast(int, value)


def _model_instructions(contract: AgentContract) -> str:
    return (
        f"{contract.prompt_template}\n\n"
        "Return JSON only. Do not take actions. "
        "The JSON must conform to this output schema: "
        f"{json.dumps(contract.output_schema, ensure_ascii=False)}"
    )


def _model_input_text(
    request: AgentRunRequest, fixture_context: tuple[dict[str, Any], ...] | list[dict[str, Any]]
) -> str:
    return json.dumps(
        {"input": request.input, "read_only_fixture_context": fixture_context},
        ensure_ascii=False,
    )


def _conservative_input_token_bound(instructions: str, input_text: str) -> int:
    """Upper-bound text tokens by UTF-8 bytes before a provider call.

    This intentionally over-reserves budget; a token cannot represent an empty
    byte sequence, so it cannot understate the user-controlled textual input.
    """
    return len((instructions + input_text).encode("utf-8"))


def _estimated_context_tokens(instructions: str, input_text: str) -> int:
    """Estimate context use before a provider call using a documented heuristic."""
    return max(1, ceil(len((instructions + input_text).encode("utf-8")) / 4))


def _parse_and_validate_output(value: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(_strip_code_fence(value))
    except json.JSONDecodeError as error:
        raise OutputSchemaError("model output was not valid JSON") from error
    if not isinstance(parsed, dict):
        raise OutputSchemaError("model output must be a JSON object")
    try:
        _validate_json_schema(parsed, schema, "output")
    except InputSchemaError as error:
        raise OutputSchemaError(str(error)) from error
    return parsed


def _validate_output_citations(
    output: dict[str, Any], fixture_context: tuple[dict[str, Any], ...]
) -> None:
    """Prevent a model from claiming sources that the Runtime did not retrieve."""
    permitted = {
        citation["citation_key"]
        for context in fixture_context
        for citation in context.get("records", [])
        if isinstance(citation, dict) and isinstance(citation.get("citation_key"), str)
    }
    if not permitted:
        return
    citations = output.get("citations")
    if not isinstance(citations, list) or not citations:
        raise OutputSchemaError("output must cite at least one retrieved source")
    supplied: set[str] = set()
    for citation in citations:
        if isinstance(citation, str):
            supplied.add(citation)
        elif isinstance(citation, dict) and isinstance(citation.get("citation_key"), str):
            supplied.add(citation["citation_key"])
        else:
            raise OutputSchemaError("each output citation must identify a citation_key")
    unknown = supplied - permitted
    if unknown:
        raise OutputSchemaError("output cited a source not retrieved by the Runtime")


def _validate_json_schema(value: Any, schema: dict[str, Any], path: str) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise InputSchemaError(f"{path} must be an object")
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    raise InputSchemaError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in value and isinstance(property_schema, dict):
                    _validate_json_schema(value[key], property_schema, f"{path}.{key}")
    elif expected_type == "array" and not isinstance(value, list):
        raise InputSchemaError(f"{path} must be an array")
    elif expected_type == "string" and not isinstance(value, str):
        raise InputSchemaError(f"{path} must be a string")
    elif expected_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise InputSchemaError(f"{path} must be an integer")
    elif expected_type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise InputSchemaError(f"{path} must be a number")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise InputSchemaError(f"{path} must be a boolean")


def _read_only_fixture(fixture_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture": "VALIDATION_READ_ONLY_PROPERTY_SOURCE",
        "query": fixture_input.get("query", ""),
        "records": [
            {
                "reference": "FIXTURE-PROPERTY-001",
                "summary": (
                    "Synthetic read-only property opportunity fixture for runtime validation."
                ),
            }
        ],
    }


def _source_query(fixture_input: dict[str, Any]) -> str:
    """Use an explicit retrieval query without asking the model to choose a source."""
    for key in ("query", "claim", "question", "division_code"):
        value = fixture_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return stripped

