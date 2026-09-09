"""PydanticAI model adapter that routes every inference through ModelGateway."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.messages import (
    ModelResponse as PydanticModelResponse,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from alos.model_gateway import (
    DataClassification,
    ModelGateway,
)
from alos.model_gateway import (
    ModelRequest as GatewayRequest,
)


class _ToolCallEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"]
    tool_name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any]
    tool_call_id: str = Field(min_length=1, max_length=200)


class _FinalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["final"]
    output: dict[str, Any]


_GatewayEnvelope = Annotated[_ToolCallEnvelope | _FinalEnvelope, Field(discriminator="type")]
_GATEWAY_ENVELOPE_ADAPTER: TypeAdapter[_GatewayEnvelope] = TypeAdapter(_GatewayEnvelope)

_PROTOCOL_INSTRUCTIONS = """You are operating inside the governed ALOS agent runtime.
Return exactly one JSON object and no prose.
To call one available function tool, return:
{"type":"tool_call","tool_name":"exact.name","arguments":{},"tool_call_id":"unique-id"}
To finish, return:
{"type":"final","output":{}}
The final output must satisfy the supplied output tool JSON schema.
Never invent a tool name. Never claim a tool result that is absent from message history.
"""


class ALOSModelAdapter(Model[None]):
    """Translate PydanticAI turns to the provider-neutral ALOS gateway."""

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        model_name: str,
        classification: DataClassification,
        correlation_id: UUID,
        max_output_tokens: int,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._model_name = model_name
        self._classification = classification
        self._correlation_id = correlation_id
        self._max_output_tokens = max_output_tokens

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return "alos-model-gateway"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> PydanticModelResponse:
        _, parameters = self.prepare_request(model_settings, model_request_parameters)
        gateway_request = GatewayRequest(
            correlation_id=self._correlation_id,
            model=self._model_name,
            instructions=_PROTOCOL_INSTRUCTIONS,
            input_text=_gateway_input(messages, parameters),
            data_classification=self._classification,
            max_output_tokens=self._max_output_tokens,
        )
        response = await asyncio.to_thread(self._gateway.generate, gateway_request)
        envelope = _GATEWAY_ENVELOPE_ADAPTER.validate_json(response.output_text)
        parts = _response_parts(envelope, parameters)
        return PydanticModelResponse(
            parts=parts,
            usage=RequestUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost=response.estimated_cost_usd,
            ),
            model_name=response.model,
            provider_name=response.provider,
            provider_details={"alos_latency_milliseconds": response.latency_milliseconds},
        )


def _gateway_input(
    messages: list[ModelMessage], parameters: ModelRequestParameters
) -> str:
    payload = {
        "messages": ModelMessagesTypeAdapter.dump_python(
            messages,
            mode="json",
            exclude_none=True,
        ),
        "function_tools": [_tool_payload(tool) for tool in parameters.function_tools],
        "output_tools": [_tool_payload(tool) for tool in parameters.output_tools],
        "allow_text_output": parameters.allow_text_output,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _tool_payload(tool: Any) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters_json_schema": tool.parameters_json_schema,
    }


def _response_parts(
    envelope: _ToolCallEnvelope | _FinalEnvelope,
    parameters: ModelRequestParameters,
) -> list[TextPart | ToolCallPart]:
    if isinstance(envelope, _ToolCallEnvelope):
        allowed_names = {tool.name for tool in parameters.function_tools}
        if envelope.tool_name not in allowed_names:
            raise ValueError("ModelGateway returned a tool outside the ALOS allowlist")
        return [
            ToolCallPart(
                tool_name=envelope.tool_name,
                args=envelope.arguments,
                tool_call_id=envelope.tool_call_id,
            )
        ]

    if parameters.output_tools:
        if len(parameters.output_tools) != 1:
            raise ValueError("ALOS supports exactly one governed output tool")
        return [
            ToolCallPart(
                tool_name=parameters.output_tools[0].name,
                args=envelope.output,
                tool_call_id="alos-final-output",
            )
        ]
    if parameters.allow_text_output:
        return [TextPart(json.dumps(envelope.output, sort_keys=True))]
    raise ValueError("ModelGateway returned final output without an allowed output mode")
