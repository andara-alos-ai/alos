from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from alos.identity import DataScope, HumanRole
from alos.runtime.agentic import ALOSToolAdapter, ExecutionContext, ExecutionMode
from alos.security.tokens import ActorContext
from alos.tools.executor import (
    StructuredToolCall,
    ToolExecutionDenied,
    ToolExecutionResult,
)


class RecordingToolExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[StructuredToolCall, dict[str, object]]] = []

    def execute(self, call: StructuredToolCall, **kwargs: object) -> ToolExecutionResult:
        self.calls.append((call, kwargs))
        return ToolExecutionResult(
            tool_key=call.tool_key,
            capability_key="records.read",
            correlation_id=kwargs["correlation_id"],  # type: ignore[arg-type]
            status="SUCCEEDED",
            output={"record_id": "REC-1"},
            elapsed_milliseconds=2,
        )


def actor() -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[uuid4()],
        data_scope=DataScope.COMPANY,
        permissions=["records.read"],
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def context(actor_context: ActorContext, **overrides: Any) -> ExecutionContext:
    values: dict[str, Any] = {
        "organization_id": actor_context.organization_id,
        "workspace_id": actor_context.workspace_ids[0],
        "actor_user_id": actor_context.user_id,
        "actor_role": actor_context.roles[0].value,
        "agent_id": uuid4(),
        "agent_version_id": uuid4(),
        "run_id": uuid4(),
        "correlation_id": uuid4(),
        "execution_mode": ExecutionMode.TEST,
        "classification": "INTERNAL",
    }
    values.update(overrides)
    return ExecutionContext(**values)


def test_tool_adapter_routes_call_with_identity_lineage_and_idempotency() -> None:
    actor_context = actor()
    execution_context = context(actor_context)
    executor = RecordingToolExecutor()
    adapter = ALOSToolAdapter(executor, actor_context)  # type: ignore[arg-type]

    output = adapter.invoke(
        execution_context,
        "records.lookup",
        {"record_id": "REC-1", "idempotency_key": "idem-0001"},
    )

    call, kwargs = executor.calls[0]
    assert call.idempotency_key == "idem-0001"
    assert kwargs["actor"] == actor_context
    assert kwargs["correlation_id"] == execution_context.correlation_id
    assert kwargs["agent_version_id"] == execution_context.agent_version_id
    assert kwargs["agent_run_id"] == execution_context.run_id
    assert output["status"] == "SUCCEEDED"


@pytest.mark.parametrize(
    "override",
    [
        {"actor_user_id": uuid4()},
        {"organization_id": uuid4()},
        {"workspace_id": uuid4()},
        {"actor_role": "OUTSIDE_ROLE"},
        {"tenant_id": uuid4()},
    ],
)
def test_tool_adapter_denies_scope_mismatch_before_executor(
    override: dict[str, UUID | str],
) -> None:
    actor_context = actor()
    executor = RecordingToolExecutor()
    adapter = ALOSToolAdapter(executor, actor_context)  # type: ignore[arg-type]

    with pytest.raises(ToolExecutionDenied):
        adapter.invoke(context(actor_context, **override), "records.lookup", {})

    assert executor.calls == []
