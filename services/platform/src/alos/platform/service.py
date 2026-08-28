from typing import Protocol
from uuid import UUID, uuid4

from alos.agents.runtime import AgentExecutionPlan, AgentRunRequest, SharedAgentRuntime
from alos.platform.models import (
    InteractionOutcome,
    LeadIntake,
    LeadIntakeResult,
    ProjectCreate,
    ProjectView,
    SalesAssignment,
    SalesInteraction,
    WorkflowActionResult,
    WorkItemView,
)
from alos.security import Principal, Role, UserCreate, UserView
from alos.security.authorization import require_any_role, require_project_access
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry


class OperationalStore(Protocol):
    def create_user(self, command: UserCreate, principal: Principal) -> UserView: ...

    def create_project(self, command: ProjectCreate, principal: Principal) -> ProjectView: ...

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]: ...

    def create_lead(
        self,
        command: LeadIntake,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> LeadIntakeResult: ...

    def list_work_items(
        self, principal: Principal, project_id: UUID | None
    ) -> tuple[WorkItemView, ...]: ...

    def assign_sales_pic(
        self,
        workflow_run_id: UUID,
        command: SalesAssignment,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
    ) -> WorkflowActionResult: ...

    def record_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan | None,
    ) -> WorkflowActionResult: ...


class OperationsService:
    def __init__(
        self,
        store: OperationalStore,
        workflows: WorkflowRegistry,
        runtime: SharedAgentRuntime,
    ) -> None:
        self._store = store
        self._workflows = workflows
        self._runtime = runtime

    def create_user(self, command: UserCreate, principal: Principal) -> UserView:
        require_any_role(principal, Role.IT_ADMIN)
        expected_division = {
            Role.SALES: "SALES_MARKETING",
            Role.FINANCE: "FINANCE",
            Role.PROPERTY: "PROPERTY",
            Role.HR: "HR",
            Role.LEGAL: "LEGAL",
            Role.IT_ADMIN: "IT",
        }.get(command.role)
        if expected_division is not None and command.division_code != expected_division:
            raise ValueError(
                f"Role {command.role.value} hanya dapat ditempatkan pada {expected_division}"
            )
        return self._store.create_user(command, principal)

    def create_project(self, command: ProjectCreate, principal: Principal) -> ProjectView:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        return self._store.create_project(command, principal)

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]:
        return self._store.list_projects(principal)

    def intake_lead(
        self,
        command: LeadIntake,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> LeadIntakeResult:
        require_any_role(principal, Role.SALES, Role.DIVISION_HEAD, Role.IT_ADMIN)
        require_project_access(principal, command.project_id)
        if not command.consent_recorded:
            raise ValueError("Consent lead wajib tercatat sebelum diproses")
        correlation_id = correlation_id or uuid4()
        definition = next(
            item for item in self._workflows.load_all() if item.workflow_id == "FLOW-001"
        )
        plan = self._runtime.prepare(
            AgentRunRequest(
                agent_id="SLA",
                capability="validate_lead_fields",
                input_references=[f"lead-intake:{idempotency_key}"],
                correlation_id=correlation_id,
                idempotency_key=f"sla-{idempotency_key}",
            )
        )
        return self._store.create_lead(
            command,
            principal,
            definition,
            plan,
            correlation_id,
            idempotency_key,
        )

    def list_work_items(
        self, principal: Principal, project_id: UUID | None = None
    ) -> tuple[WorkItemView, ...]:
        if project_id is not None:
            require_project_access(principal, project_id)
        return self._store.list_work_items(principal, project_id)

    def assign_sales_pic(
        self,
        workflow_run_id: UUID,
        command: SalesAssignment,
        principal: Principal,
        idempotency_key: str,
    ) -> WorkflowActionResult:
        require_any_role(principal, Role.SALES, Role.DIVISION_HEAD, Role.IT_ADMIN)
        definition = self._lead_workflow()
        plan = self._runtime.prepare(
            AgentRunRequest(
                agent_id="CFA",
                capability="schedule_follow_up_task",
                input_references=[f"workflow-run:{workflow_run_id}"],
                requested_tools=["alos.work_item.create"],
                correlation_id=uuid4(),
                idempotency_key=f"cfa-{idempotency_key}",
            )
        )
        return self._store.assign_sales_pic(workflow_run_id, command, principal, definition, plan)

    def record_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        idempotency_key: str,
    ) -> WorkflowActionResult:
        require_any_role(principal, Role.SALES, Role.DIVISION_HEAD, Role.IT_ADMIN)
        definition = self._lead_workflow()
        plan = None
        if command.outcome == InteractionOutcome.FOLLOW_UP:
            plan = self._runtime.prepare(
                AgentRunRequest(
                    agent_id="CFA",
                    capability="schedule_follow_up_task",
                    input_references=[f"workflow-run:{workflow_run_id}"],
                    requested_tools=["alos.work_item.create"],
                    correlation_id=uuid4(),
                    idempotency_key=f"cfa-{idempotency_key}",
                )
            )
        return self._store.record_sales_interaction(
            workflow_run_id, command, principal, definition, plan
        )

    def _lead_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-001")
