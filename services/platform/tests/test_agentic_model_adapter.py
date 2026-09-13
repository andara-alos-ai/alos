import json
from decimal import Decimal
from uuid import uuid4

from alos.model_gateway import (
    FakeModelGateway,
    ModelGatewayBudgetError,
    ModelResponse,
    ModelUsage,
)
from alos.runtime.agentic import (
    AgenticExecutionRequest,
    AgenticToolDefinition,
    ALOSModelAdapter,
    ExecutionContext,
    ExecutionLimits,
    ExecutionMode,
    ExecutionStatus,
    PydanticAgenticEngine,
)


class RecordingInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke(
        self,
        context: ExecutionContext,
        tool_key: str,
        arguments: dict[str, object],
    ) -> object:
        self.calls.append((tool_key, arguments))
        return {"record_id": "REC-1", "status": "AVAILABLE"}


def gateway_response(payload: dict[str, object]) -> ModelResponse:
    return ModelResponse(
        provider="fake",
        model="alos-test-route",
        output_text=json.dumps(payload),
        usage=ModelUsage(input_tokens=12, output_tokens=8),
        latency_milliseconds=4,
        estimated_cost_usd=Decimal("0.002"),
    )


def execution_request(*, with_tool: bool = False) -> AgenticExecutionRequest:
    tools: tuple[AgenticToolDefinition, ...] = ()
    if with_tool:
        tools = (
            AgenticToolDefinition(
                tool_key="records.lookup",
                description="Look up one approved record.",
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"record_id": {"type": "string"}},
                    "required": ["record_id"],
                },
            ),
        )
    return AgenticExecutionRequest(
        context=ExecutionContext(
            organization_id=uuid4(),
            workspace_id=uuid4(),
            actor_user_id=uuid4(),
            actor_role="TEST_OPERATOR",
            agent_id=uuid4(),
            agent_version_id=uuid4(),
            run_id=uuid4(),
            correlation_id=uuid4(),
            execution_mode=ExecutionMode.TEST,
            classification="INTERNAL",
        ),
        instructions="Return a governed structured result.",
        input_text="Inspect approved data only.",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        },
        tools=tools,
        limits=ExecutionLimits(),
    )


def engine(gateway: FakeModelGateway, request: AgenticExecutionRequest, invoker: object = None):
    adapter = ALOSModelAdapter(
        gateway,
        model_name="alos-test-route",
        classification=request.context.classification,
        correlation_id=request.context.correlation_id,
        max_output_tokens=request.limits.max_output_tokens,
    )
    return PydanticAgenticEngine(adapter, invoker)  # type: ignore[arg-type]


def test_model_adapter_routes_final_output_and_accounting_through_gateway() -> None:
    request = execution_request()
    gateway = FakeModelGateway(
        [gateway_response({"type": "final", "output": {"result": "governed"}})]
    )

    result = engine(gateway, request).execute(request)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output == {"result": "governed"}
    assert result.usage.total_model_calls == 1
    assert result.usage.total_cost == Decimal("0.002")
    assert gateway.requests[0].correlation_id == request.context.correlation_id
    assert gateway.requests[0].data_classification == "INTERNAL"


def test_model_adapter_completes_tool_loop_without_bypassing_invoker() -> None:
    request = execution_request(with_tool=True)
    gateway = FakeModelGateway(
        [
            gateway_response(
                {
                    "type": "tool_call",
                    "tool_name": "records.lookup",
                    "arguments": {"record_id": "REC-1"},
                    "tool_call_id": "call-1",
                }
            ),
            gateway_response({"type": "final", "output": {"result": "found"}}),
        ]
    )
    invoker = RecordingInvoker()

    result = engine(gateway, request, invoker).execute(request)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output == {"result": "found"}
    assert result.usage.total_model_calls == 2
    assert result.usage.total_tool_calls == 1
    assert invoker.calls == [("records.lookup", {"record_id": "REC-1"})]
    assert "tool-return" in gateway.requests[1].input_text


def test_model_adapter_rejects_tool_name_outside_allowlist() -> None:
    request = execution_request(with_tool=True)
    gateway = FakeModelGateway(
        [
            gateway_response(
                {
                    "type": "tool_call",
                    "tool_name": "records.delete",
                    "arguments": {},
                    "tool_call_id": "call-1",
                }
            )
        ]
    )

    result = engine(gateway, request, RecordingInvoker()).execute(request)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == "AGENTIC_EXECUTION_FAILED"


def test_model_gateway_budget_error_is_a_controlled_block() -> None:
    request = execution_request()
    gateway = FakeModelGateway(
        [ModelGatewayBudgetError("COST_LIMIT", "synthetic budget refusal")]
    )

    result = engine(gateway, request).execute(request)

    assert result.status == ExecutionStatus.BLOCKED
    assert result.error_code == "MODEL_BUDGET_EXCEEDED"
