from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentDefinition, AgentReference
from alos.agents.registry import AgentRegistry
from alos.agents.runtime.models import (
    AgentCapabilityExecuteRequest,
    AgentCapabilityExecutionView,
    AgentExecutionPlan,
    AgentRunRequest,
)
from alos.agents.runtime.service import SharedAgentRuntime
from alos.security import Principal, Role
from alos.security.authorization import (
    AuthorizationDenied,
    require_any_role,
    require_project_access,
)


class StandaloneAgentRunStore(Protocol):
    def record_standalone_agent_run(
        self,
        plan: AgentExecutionPlan,
        principal: Principal,
        project_id: UUID | None,
    ) -> None: ...

    def record_agent_lifecycle_transition(
        self,
        before: AgentDefinition,
        after: AgentDefinition,
        principal: Principal,
        action: str,
        reason: str,
        correlation_id: UUID,
    ) -> None: ...


DOMAIN_ROLES: dict[str, tuple[Role, ...]] = {
    "finance": (Role.FINANCE,),
    "sales-marketing": (Role.SALES,),
    "property": (Role.PROPERTY,),
    "hr": (Role.HR,),
    "legal": (Role.LEGAL,),
    "shared-enterprise": (
        Role.DIRECTOR,
        Role.AI_EXECUTIVE,
        Role.DIVISION_HEAD,
        Role.SALES,
        Role.FINANCE,
        Role.PROPERTY,
        Role.HR,
        Role.LEGAL,
        Role.IT_ADMIN,
    ),
}


class AgentCapabilityService:
    def __init__(
        self,
        agents: AgentRegistry,
        capabilities: CapabilityRegistry,
        runtime: SharedAgentRuntime,
        store: StandaloneAgentRunStore,
    ) -> None:
        self._agents = agents
        self._capabilities = capabilities
        self._runtime = runtime
        self._store = store

    def execute(
        self,
        command: AgentCapabilityExecuteRequest,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> AgentCapabilityExecutionView:
        agent = self._agents.get(command.agent_id, command.agent_version)
        allowed_roles = DOMAIN_ROLES.get(agent.domain)
        if allowed_roles is None:
            raise AuthorizationDenied(f"Domain agent tidak didukung: {agent.domain}")
        require_any_role(principal, *allowed_roles)
        if (
            agent.division_scope
            and not principal.has_any_role(Role.DIRECTOR, Role.AI_EXECUTIVE)
            and not (set(principal.division_codes) & set(agent.division_scope))
        ):
            raise AuthorizationDenied(
                "Pengguna tidak memiliki konteks divisi yang diizinkan Agent Contract"
            )
        if command.project_id is not None:
            require_project_access(principal, command.project_id)
        capability = self._capabilities.get(command.capability)
        correlation_id = correlation_id or uuid4()
        plan = self._runtime.prepare(
            AgentRunRequest(
                agent_id=agent.agent_id,
                agent_version=agent.version,
                capability=command.capability,
                execution_mode=capability.execution_mode,
                input_references=command.input_references,
                requested_tools=command.requested_tools,
                material_action=True,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
        )
        payload = dict(command.input_payload)
        payload["data_classification"] = command.data_classification
        if capability.execution_mode.value == "AI_ASSISTED":
            payload.setdefault("source_reference", command.input_references[0])
        executed = self._runtime.execute(plan, payload)
        if executed.execution is None:
            raise RuntimeError("Runtime tidak menghasilkan execution record")
        self._store.record_standalone_agent_run(
            executed, principal, command.project_id
        )
        result = executed.execution
        return AgentCapabilityExecutionView(
            run_id=executed.run_id,
            agent_id=executed.agent_id,
            agent_version=executed.agent_version,
            capability=executed.capability,
            status=result.status,
            handler_id=result.handler_id,
            output_reference=result.output_reference,
            evidence_references=result.evidence_references,
            warnings=result.warnings,
            verification_status=result.verification_status,
            requires_human_review=executed.requires_human_review,
            correlation_id=executed.correlation_id,
        )


class AgentLifecycleService:
    """Human-only lifecycle controls for generated logical agents."""

    def __init__(self, agents: AgentRegistry, store: StandaloneAgentRunStore) -> None:
        self._agents = agents
        self._store = store

    def activate(
        self,
        agent_id: str,
        version: str,
        principal: Principal,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> AgentDefinition:
        return self._change(
            agent_id,
            version,
            principal,
            reason,
            correlation_id,
            "agent.activated",
            lambda: self._agents.activate_generated(agent_id, version),
        )

    def suspend(
        self,
        agent_id: str,
        version: str,
        principal: Principal,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> AgentDefinition:
        return self._change(
            agent_id,
            version,
            principal,
            reason,
            correlation_id,
            "agent.suspended",
            lambda: self._agents.suspend_generated(agent_id, version),
        )

    def rollback(
        self,
        agent_id: str,
        version: str,
        target: AgentReference,
        principal: Principal,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> AgentDefinition:
        return self._change(
            agent_id,
            version,
            principal,
            reason,
            correlation_id,
            "agent.rolled_back",
            lambda: self._agents.rollback_generated(agent_id, version, target),
        )

    def _change(
        self,
        agent_id: str,
        version: str,
        principal: Principal,
        reason: str,
        correlation_id: UUID | None,
        action: str,
        change: Callable[[], AgentDefinition],
    ) -> AgentDefinition:
        require_any_role(principal, Role.IT_ADMIN)
        before = self._agents.get(agent_id, version)
        after = change()
        self._store.record_agent_lifecycle_transition(
            before,
            after,
            principal,
            action,
            reason,
            correlation_id or uuid4(),
        )
        return after
