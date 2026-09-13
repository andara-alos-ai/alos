"""Only permitted bridge from PydanticAI tools to the ALOS ToolExecutor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from alos.runtime.agentic.output import ExecutionContext
from alos.security.tokens import ActorContext
from alos.tools.executor import (
    StructuredToolCall,
    ToolExecutionDenied,
    ToolExecutor,
)


class ALOSToolAdapter:
    """Bind immutable execution scope to the authoritative ToolExecutor."""

    def __init__(self, executor: ToolExecutor, actor: ActorContext) -> None:
        self._executor = executor
        self._actor = actor

    def invoke(
        self,
        context: ExecutionContext,
        tool_key: str,
        arguments: dict[str, Any],
    ) -> Any:
        self._validate_actor_scope(context)
        idempotency_key = arguments.get("idempotency_key")
        call = StructuredToolCall(
            tool_key=tool_key,
            arguments=arguments,
            idempotency_key=str(idempotency_key) if idempotency_key is not None else None,
        )
        tracer = trace.get_tracer("alos.runtime.agentic.tool")
        with tracer.start_as_current_span("alos.tool_executor.execute") as span:
            span.set_attribute("alos.correlation_id", str(context.correlation_id))
            span.set_attribute("alos.tool_key", tool_key)
            result = self._executor.execute(
                call,
                actor=self._actor,
                correlation_id=context.correlation_id,
                agent_version_id=context.agent_version_id,
                agent_run_id=context.run_id,
            )
            span.set_attribute("alos.tool_status", result.status)
            span.set_attribute("alos.tool_latency_ms", result.elapsed_milliseconds)
        return result.model_dump(mode="json")

    def _validate_actor_scope(self, context: ExecutionContext) -> None:
        if self._actor.expires_at <= datetime.now(UTC):
            raise ToolExecutionDenied("actor context has expired")
        if context.actor_user_id != self._actor.user_id:
            raise ToolExecutionDenied("execution actor does not match authenticated actor")
        if context.organization_id != self._actor.organization_id:
            raise ToolExecutionDenied("execution organization is outside the actor scope")
        if context.workspace_id not in self._actor.workspace_ids:
            raise ToolExecutionDenied("execution workspace is outside the actor scope")
        if context.actor_role not in {role.value for role in self._actor.roles}:
            raise ToolExecutionDenied("execution role is outside the actor scope")
        if context.tenant_id is not None:
            raise ToolExecutionDenied(
                "tenant-scoped tool execution requires tenant-aware ToolExecutor support"
            )
