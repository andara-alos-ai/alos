from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from alos.agents.registry import AgentRegistry
from alos.agents.runtime import AgentExecutionPlan, SharedAgentRuntime
from alos.platform import (
    LeadIntake,
    LeadIntakeResult,
    ProjectCreate,
    ProjectView,
    WorkItemStatus,
)
from alos.platform.service import OperationsService
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class RecordingStore:
    def __init__(self) -> None:
        self.received_plan: AgentExecutionPlan | None = None

    def create_project(self, command: ProjectCreate, principal: Principal) -> ProjectView:
        return ProjectView(
            project_id=uuid4(),
            organization_id=principal.organization_id,
            code=command.code,
            name=command.name,
            status="DRAFT",
            created_at=datetime.now(UTC),
        )

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]:
        return ()

    def create_lead(
        self,
        command: LeadIntake,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> LeadIntakeResult:
        self.received_plan = agent_plan
        return LeadIntakeResult(
            lead_id=uuid4(),
            work_item_id=uuid4(),
            workflow_run_id=uuid4(),
            current_step="sales-assignment",
            work_item_status=WorkItemStatus.NEEDS_REVIEW,
            due_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )

    def list_work_items(self, principal: Principal, project_id: UUID | None) -> tuple[()]:
        return ()


def service(store: RecordingStore) -> OperationsService:
    definitions = REPOSITORY_ROOT / "definitions"
    return OperationsService(
        store,
        WorkflowRegistry(definitions),
        SharedAgentRuntime(AgentRegistry(definitions)),
    )


def sales_principal(project_id: UUID) -> Principal:
    return Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.SALES}),
        division_codes=frozenset({"SALES_MARKETING"}),
        project_ids=frozenset({project_id}),
    )


def test_lead_intake_runs_sla_validation_and_stops_for_human_assignment() -> None:
    store = RecordingStore()
    project_id = uuid4()

    result = service(store).intake_lead(
        LeadIntake(
            project_id=project_id,
            full_name="Lead Sintetis",
            phone="081234567890",
            source="form-internal",
            consent_recorded=True,
        ),
        sales_principal(project_id),
        "lead-test-001",
    )

    assert result.current_step == "sales-assignment"
    assert result.work_item_status == WorkItemStatus.NEEDS_REVIEW
    assert store.received_plan is not None
    assert store.received_plan.agent_id == "SLA"
    assert store.received_plan.capability == "validate_lead_fields"


def test_lead_intake_blocks_missing_consent() -> None:
    store = RecordingStore()
    project_id = uuid4()

    with pytest.raises(ValueError, match="Consent"):
        service(store).intake_lead(
            LeadIntake(
                project_id=project_id,
                full_name="Lead Sintetis",
                email="lead@example.test",
                source="form-internal",
                consent_recorded=False,
            ),
            sales_principal(project_id),
            "lead-test-002",
        )


def test_sales_cannot_create_project() -> None:
    project_id = uuid4()

    with pytest.raises(AuthorizationDenied):
        service(RecordingStore()).create_project(
            ProjectCreate(code="PILOT", name="Proyek Pilot"),
            sales_principal(project_id),
        )
