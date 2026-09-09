from uuid import uuid4

from pydantic_ai.models.test import TestModel

from alos.runtime.agentic import (
    AgenticExecutionRequest,
    AgenticToolDefinition,
    ExecutionContext,
    ExecutionLimits,
    ExecutionMode,
    ExecutionStatus,
    PydanticAgenticEngine,
)


class NoopInvoker:
    def invoke(
        self,
        context: ExecutionContext,
        tool_key: str,
        arguments: dict[str, object],
    ) -> object:
        return {"tool_key": tool_key, "arguments": arguments}


def request(
    *, max_model_steps: int = 2, tools: tuple[AgenticToolDefinition, ...] = ()
) -> AgenticExecutionRequest:
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
        instructions="Return a structured test response.",
        input_text="Run the synthetic scenario.",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        },
        tools=tools,
        limits=ExecutionLimits(max_model_steps=max_model_steps),
    )


def test_pydantic_engine_returns_structured_output_and_cumulative_usage() -> None:
    engine = PydanticAgenticEngine(TestModel(custom_output_args={"result": "ok"}))

    result = engine.execute(request())

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output == {"result": "ok"}
    assert result.usage.total_model_calls == 1
    assert result.usage.total_tokens == (
        result.usage.total_input_tokens + result.usage.total_output_tokens
    )
    assert result.steps[-1].status == ExecutionStatus.SUCCEEDED


def test_pydantic_engine_converts_request_limit_into_controlled_block() -> None:
    engine = PydanticAgenticEngine(
        TestModel(call_tools="all", custom_output_args={"result": "ok"}),
        NoopInvoker(),
    )
    bounded = request(
        max_model_steps=1,
        tools=(
            AgenticToolDefinition(
                tool_key="records.lookup",
                description="Read a synthetic record.",
                input_schema={"type": "object", "properties": {}},
            ),
        ),
    )

    result = engine.execute(bounded)

    assert result.status == ExecutionStatus.BLOCKED
    assert result.error_code == "RUNTIME_LIMIT_EXCEEDED"


def test_pydantic_engine_cancel_is_false_for_unknown_or_completed_run() -> None:
    engine = PydanticAgenticEngine(TestModel(custom_output_args={"result": "ok"}))
    execution_request = request()

    assert not engine.cancel(execution_request.context.run_id)
    assert engine.execute(execution_request).status == ExecutionStatus.SUCCEEDED
    assert not engine.cancel(execution_request.context.run_id)
