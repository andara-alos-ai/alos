from typing import Protocol
from uuid import UUID, uuid4

from alos.agents.runtime import AgentExecutionPlan, SharedAgentRuntime
from alos.platform.models import (
    ApprovalDecisionCreate,
    ApprovalRequestCreate,
    ApprovalRequestView,
    BudgetCreate,
    BudgetView,
    CapaCreate,
    CapaView,
    DocumentCreate,
    DocumentView,
    EvidenceCreate,
    EvidenceView,
    ExceptionCreate,
    ExceptionView,
    ExecutiveBriefCreate,
    ExecutiveBriefResult,
    ExecutiveBriefReviewCreate,
    FinanceWorkflowResult,
    InteractionOutcome,
    LeadIntake,
    LeadIntakeResult,
    LegalReviewCreate,
    LegalSubmissionCreate,
    LegalWorkflowResult,
    PaymentDecisionCreate,
    PaymentRecordCreate,
    PaymentRequestCreate,
    PaymentRequestView,
    ProjectCreate,
    ProjectView,
    PropertyReviewCreate,
    PropertyWorkflowResult,
    ReconciliationCreate,
    RecruitmentDecisionCreate,
    RecruitmentRequestCreate,
    RecruitmentWorkflowResult,
    SalesAssignment,
    SalesInteraction,
    SiteEvidenceCreate,
    WorkflowActionResult,
    WorkItemView,
)
from alos.security import Principal, Role, UserCreate, UserView
from alos.security.authorization import (
    AuthorizationDenied,
    require_any_role,
    require_division_role,
    require_project_access,
)
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry


class OperationalStore(Protocol):
    def create_budget(self, command: BudgetCreate, principal: Principal) -> BudgetView: ...

    def create_payment_request(
        self,
        command: PaymentRequestCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> PaymentRequestView: ...

    def decide_payment(
        self,
        payment_request_id: UUID,
        command: PaymentDecisionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> FinanceWorkflowResult: ...

    def record_payment(
        self,
        payment_request_id: UUID,
        command: PaymentRecordCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> FinanceWorkflowResult: ...

    def reconcile_payment(
        self,
        payment_request_id: UUID,
        command: ReconciliationCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plan: AgentExecutionPlan,
    ) -> FinanceWorkflowResult: ...

    def submit_site_evidence(
        self,
        command: SiteEvidenceCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> PropertyWorkflowResult: ...

    def review_site_evidence(
        self,
        site_evidence_id: UUID,
        command: PropertyReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plan: AgentExecutionPlan,
    ) -> PropertyWorkflowResult: ...

    def submit_legal_document(
        self,
        command: LegalSubmissionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> LegalWorkflowResult: ...

    def review_legal_document(
        self,
        legal_case_id: UUID,
        command: LegalReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> LegalWorkflowResult: ...

    def submit_recruitment_request(
        self,
        command: RecruitmentRequestCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> RecruitmentWorkflowResult: ...

    def decide_recruitment(
        self,
        recruitment_request_id: UUID,
        command: RecruitmentDecisionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan | None,
    ) -> RecruitmentWorkflowResult: ...

    def generate_executive_brief(
        self,
        command: ExecutiveBriefCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutiveBriefResult: ...

    def review_executive_brief(
        self,
        executive_brief_id: UUID,
        command: ExecutiveBriefReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> ExecutiveBriefResult: ...

    def create_document(self, command: DocumentCreate, principal: Principal) -> DocumentView: ...

    def create_evidence(self, command: EvidenceCreate, principal: Principal) -> EvidenceView: ...

    def request_approval(
        self, command: ApprovalRequestCreate, principal: Principal
    ) -> ApprovalRequestView: ...

    def decide_approval(
        self,
        approval_request_id: UUID,
        command: ApprovalDecisionCreate,
        principal: Principal,
    ) -> ApprovalRequestView: ...

    def create_exception(self, command: ExceptionCreate, principal: Principal) -> ExceptionView: ...

    def create_capa(self, command: CapaCreate, principal: Principal) -> CapaView: ...

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
        organization_roles = {Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR}
        if command.role in organization_roles and command.division_code is not None:
            raise ValueError(f"Role {command.role.value} tidak ditempatkan pada divisi")
        if command.role == Role.DIVISION_HEAD and command.division_code is None:
            raise ValueError("Role DIVISION_HEAD wajib memiliki divisi")
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

    def create_budget(self, command: BudgetCreate, principal: Principal) -> BudgetView:
        require_division_role(principal, "FINANCE", Role.FINANCE)
        require_project_access(principal, command.project_id)
        return self._store.create_budget(command, principal)

    def create_payment_request(
        self,
        command: PaymentRequestCreate,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> PaymentRequestView:
        require_division_role(principal, "FINANCE", Role.FINANCE)
        require_project_access(principal, command.project_id)
        correlation_id = correlation_id or uuid4()
        definition = self._payment_workflow()
        plans = self._prepare_agent_steps(
            definition,
            ("document-extraction", "evidence-check", "budget-check", "approval-routing"),
            [f"payment-request:{idempotency_key}"],
            correlation_id,
            idempotency_key,
        )
        return self._store.create_payment_request(
            command, principal, definition, plans, correlation_id, idempotency_key
        )

    def decide_payment(
        self, payment_request_id: UUID, command: PaymentDecisionCreate, principal: Principal
    ) -> FinanceWorkflowResult:
        require_division_role(principal, "FINANCE", Role.FINANCE)
        return self._store.decide_payment(
            payment_request_id, command, principal, self._payment_workflow()
        )

    def record_payment(
        self, payment_request_id: UUID, command: PaymentRecordCreate, principal: Principal
    ) -> FinanceWorkflowResult:
        require_division_role(principal, "FINANCE", Role.FINANCE)
        return self._store.record_payment(
            payment_request_id, command, principal, self._payment_workflow()
        )

    def reconcile_payment(
        self,
        payment_request_id: UUID,
        command: ReconciliationCreate,
        principal: Principal,
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        require_division_role(principal, "FINANCE", Role.FINANCE)
        definition = self._payment_workflow()
        plan = self._prepare_agent_step(
            definition,
            "reconciliation",
            [f"payment-request:{payment_request_id}"],
            uuid4(),
            idempotency_key,
        )
        return self._store.reconcile_payment(
            payment_request_id, command, principal, definition, plan
        )

    def submit_site_evidence(
        self,
        command: SiteEvidenceCreate,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> PropertyWorkflowResult:
        require_division_role(principal, "PROPERTY", Role.PROPERTY)
        require_project_access(principal, command.project_id)
        correlation_id = correlation_id or uuid4()
        definition = self._property_workflow()
        plans = self._prepare_agent_steps(
            definition,
            ("evidence-check", "progress-verification"),
            [f"site-evidence:{idempotency_key}"],
            correlation_id,
            idempotency_key,
        )
        return self._store.submit_site_evidence(
            command,
            principal,
            definition,
            plans,
            correlation_id,
            idempotency_key,
        )

    def review_site_evidence(
        self,
        site_evidence_id: UUID,
        command: PropertyReviewCreate,
        principal: Principal,
        idempotency_key: str,
    ) -> PropertyWorkflowResult:
        require_division_role(principal, "PROPERTY", Role.PROPERTY)
        definition = self._property_workflow()
        step_id = "kpi-updated" if command.decision == "ACCEPTED" else "capa-open"
        plan = self._prepare_agent_step(
            definition,
            step_id,
            [f"site-evidence:{site_evidence_id}"],
            uuid4(),
            idempotency_key,
        )
        return self._store.review_site_evidence(
            site_evidence_id, command, principal, definition, plan
        )

    def submit_legal_document(
        self,
        command: LegalSubmissionCreate,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> LegalWorkflowResult:
        require_division_role(principal, "LEGAL", Role.LEGAL)
        require_project_access(principal, command.project_id)
        correlation_id = correlation_id or uuid4()
        definition = self._legal_workflow()
        input_references = [f"legal-document:{command.document_version_id}"]
        plans = (
            *self._runtime.prepare_workflow_step(
                definition,
                "document-extraction",
                input_references,
                correlation_id,
                idempotency_key,
            ),
            *self._runtime.prepare_workflow_step(
                definition,
                "legal-analysis",
                input_references,
                correlation_id,
                idempotency_key,
                selector=command.document_type,
            ),
            *self._runtime.prepare_workflow_step(
                definition,
                "evidence-check",
                input_references,
                correlation_id,
                idempotency_key,
            ),
        )
        return self._store.submit_legal_document(
            command,
            principal,
            definition,
            plans,
            correlation_id,
            idempotency_key,
        )

    def review_legal_document(
        self,
        legal_case_id: UUID,
        command: LegalReviewCreate,
        principal: Principal,
    ) -> LegalWorkflowResult:
        require_division_role(principal, "LEGAL", Role.LEGAL)
        return self._store.review_legal_document(
            legal_case_id, command, principal, self._legal_workflow()
        )

    def submit_recruitment_request(
        self,
        command: RecruitmentRequestCreate,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> RecruitmentWorkflowResult:
        hr_operator = principal.has_any_role(Role.HR) and "HR" in principal.division_codes
        division_requester = (
            principal.has_any_role(Role.DIVISION_HEAD)
            and command.requesting_division_code in principal.division_codes
        )
        if not hr_operator and not division_requester:
            raise AuthorizationDenied(
                "Recruitment request hanya dapat diajukan HR atau kepala divisi pemohon"
            )
        require_project_access(principal, command.project_id)
        correlation_id = correlation_id or uuid4()
        definition = self._hr_workflow()
        plans = self._prepare_agent_steps(
            definition,
            ("sop-plan", "candidate-screening"),
            [f"recruitment-request:{idempotency_key}"],
            correlation_id,
            idempotency_key,
        )
        return self._store.submit_recruitment_request(
            command,
            principal,
            definition,
            plans,
            correlation_id,
            idempotency_key,
        )

    def decide_recruitment(
        self,
        recruitment_request_id: UUID,
        command: RecruitmentDecisionCreate,
        principal: Principal,
        idempotency_key: str,
    ) -> RecruitmentWorkflowResult:
        require_division_role(principal, "HR", Role.HR)
        plan = None
        if command.decision == "SELECTED":
            plan = self._prepare_agent_step(
                self._hr_workflow(),
                "onboarding-checklist",
                [f"recruitment-request:{recruitment_request_id}"],
                uuid4(),
                idempotency_key,
            )
        return self._store.decide_recruitment(
            recruitment_request_id, command, principal, self._hr_workflow(), plan
        )

    def generate_executive_brief(
        self,
        command: ExecutiveBriefCreate,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> ExecutiveBriefResult:
        require_any_role(principal, Role.DIRECTOR, Role.AI_EXECUTIVE)
        if command.project_id is not None:
            require_project_access(principal, command.project_id)
        correlation_id = correlation_id or uuid4()
        definition = self._executive_workflow()
        plans = self._prepare_agent_steps(
            definition,
            ("kpi-aggregation", "risk-aggregation", "approval-aggregation", "brief-generation"),
            [f"executive-period:{command.period_start}:{command.period_end}"],
            correlation_id,
            idempotency_key,
        )
        return self._store.generate_executive_brief(
            command,
            principal,
            definition,
            plans,
            correlation_id,
            idempotency_key,
        )

    def review_executive_brief(
        self,
        executive_brief_id: UUID,
        command: ExecutiveBriefReviewCreate,
        principal: Principal,
    ) -> ExecutiveBriefResult:
        require_any_role(principal, Role.DIRECTOR)
        return self._store.review_executive_brief(
            executive_brief_id, command, principal, self._executive_workflow()
        )

    def create_document(self, command: DocumentCreate, principal: Principal) -> DocumentView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.DIVISION_HEAD,
            Role.SALES,
            Role.FINANCE,
            Role.PROPERTY,
            Role.HR,
            Role.LEGAL,
            Role.IT_ADMIN,
        )
        if command.project_id:
            require_project_access(principal, command.project_id)
        return self._store.create_document(command, principal)

    def create_evidence(self, command: EvidenceCreate, principal: Principal) -> EvidenceView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.DIVISION_HEAD,
            Role.SALES,
            Role.FINANCE,
            Role.PROPERTY,
            Role.HR,
            Role.LEGAL,
            Role.IT_ADMIN,
        )
        return self._store.create_evidence(command, principal)

    def request_approval(
        self, command: ApprovalRequestCreate, principal: Principal
    ) -> ApprovalRequestView:
        require_any_role(
            principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.FINANCE, Role.LEGAL, Role.IT_ADMIN
        )
        return self._store.request_approval(command, principal)

    def decide_approval(
        self,
        approval_request_id: UUID,
        command: ApprovalDecisionCreate,
        principal: Principal,
    ) -> ApprovalRequestView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.FINANCE, Role.LEGAL)
        return self._store.decide_approval(approval_request_id, command, principal)

    def create_exception(self, command: ExceptionCreate, principal: Principal) -> ExceptionView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.IT_ADMIN)
        if command.work_item_id is None:
            require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        return self._store.create_exception(command, principal)

    def create_capa(self, command: CapaCreate, principal: Principal) -> CapaView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.IT_ADMIN)
        return self._store.create_capa(command, principal)

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]:
        return self._store.list_projects(principal)

    def intake_lead(
        self,
        command: LeadIntake,
        principal: Principal,
        idempotency_key: str,
        correlation_id: UUID | None = None,
    ) -> LeadIntakeResult:
        require_division_role(principal, "SALES_MARKETING", Role.SALES)
        require_project_access(principal, command.project_id)
        if not command.consent_recorded:
            raise ValueError("Consent lead wajib tercatat sebelum diproses")
        correlation_id = correlation_id or uuid4()
        definition = self._lead_workflow()
        plan = self._prepare_agent_step(
            definition,
            "lead-validation",
            [f"lead-intake:{idempotency_key}"],
            correlation_id,
            idempotency_key,
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
        require_division_role(principal, "SALES_MARKETING", Role.SALES)
        definition = self._lead_workflow()
        plan = self._prepare_agent_step(
            definition,
            "follow-up-plan",
            [f"workflow-run:{workflow_run_id}"],
            uuid4(),
            idempotency_key,
        )
        return self._store.assign_sales_pic(workflow_run_id, command, principal, definition, plan)

    def record_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        idempotency_key: str,
    ) -> WorkflowActionResult:
        require_division_role(principal, "SALES_MARKETING", Role.SALES)
        definition = self._lead_workflow()
        plan = None
        if command.outcome == InteractionOutcome.FOLLOW_UP:
            plan = self._prepare_agent_step(
                definition,
                "follow-up-plan",
                [f"workflow-run:{workflow_run_id}"],
                uuid4(),
                idempotency_key,
            )
        return self._store.record_sales_interaction(
            workflow_run_id, command, principal, definition, plan
        )

    def _prepare_agent_steps(
        self,
        definition: WorkflowDefinition,
        step_ids: tuple[str, ...],
        input_references: list[str],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> tuple[AgentExecutionPlan, ...]:
        return tuple(
            plan
            for step_id in step_ids
            for plan in self._runtime.prepare_workflow_step(
                definition,
                step_id,
                input_references,
                correlation_id,
                idempotency_key,
            )
        )

    def _prepare_agent_step(
        self,
        definition: WorkflowDefinition,
        step_id: str,
        input_references: list[str],
        correlation_id: UUID,
        idempotency_key: str,
        selector: str | None = None,
    ) -> AgentExecutionPlan:
        plans = self._runtime.prepare_workflow_step(
            definition,
            step_id,
            input_references,
            correlation_id,
            idempotency_key,
            selector,
        )
        if len(plans) != 1:
            raise ValueError(f"Langkah {definition.workflow_id}/{step_id} wajib tepat satu agent")
        return plans[0]

    def _lead_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-001")

    def _payment_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-002")

    def _property_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-003")

    def _legal_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-004")

    def _hr_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-005")

    def _executive_workflow(self) -> WorkflowDefinition:
        return self._workflows.get("FLOW-006")
