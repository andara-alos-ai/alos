from typing import Protocol
from uuid import UUID, uuid4

from alos.agents.runtime import AgentExecutionPlan, AgentRunRequest, SharedAgentRuntime
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
        plans = tuple(
            self._runtime.prepare(
                AgentRunRequest(
                    agent_id=agent_id,
                    capability=capability,
                    input_references=[f"payment-request:{idempotency_key}"],
                    requested_tools=tools,
                    correlation_id=correlation_id,
                    idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
                )
            )
            for agent_id, capability, tools in (
                ("DIA", "extract_structured_fields", ["alos.document.read"]),
                ("CEA", "check_completeness", ["alos.evidence.read"]),
                ("BCA", "check_budget_deterministically", ["deterministic.calculator"]),
                ("ARA", "check_separation_of_duties", ["alos.identity.read"]),
            )
        )
        return self._store.create_payment_request(
            command, principal, self._payment_workflow(), plans, correlation_id, idempotency_key
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
        plan = self._runtime.prepare(
            AgentRunRequest(
                agent_id="FRA",
                capability="match_transactions_deterministically",
                input_references=[f"payment-request:{payment_request_id}"],
                requested_tools=["deterministic.calculator"],
                correlation_id=uuid4(),
                idempotency_key=f"fra-{idempotency_key}",
            )
        )
        return self._store.reconcile_payment(
            payment_request_id, command, principal, self._payment_workflow(), plan
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
        plans = tuple(
            self._runtime.prepare(
                AgentRunRequest(
                    agent_id=agent_id,
                    capability=capability,
                    input_references=[f"site-evidence:{idempotency_key}"],
                    requested_tools=tools,
                    correlation_id=correlation_id,
                    idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
                )
            )
            for agent_id, capability, tools in (
                ("CEA", "validate_evidence_metadata", ["alos.evidence.read"]),
                ("TPA", "calculate_progress_variance", ["deterministic.calculator"]),
            )
        )
        return self._store.submit_site_evidence(
            command,
            principal,
            self._property_workflow(),
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
        agent_id, capability, tools = (
            ("KDA", "publish_kpi_snapshot", ["alos.kpi_snapshot.create"])
            if command.decision == "ACCEPTED"
            else ("CRA", "classify_exception", ["alos.exception.create"])
        )
        plan = self._runtime.prepare(
            AgentRunRequest(
                agent_id=agent_id,
                capability=capability,
                input_references=[f"site-evidence:{site_evidence_id}"],
                requested_tools=tools,
                correlation_id=uuid4(),
                idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
            )
        )
        return self._store.review_site_evidence(
            site_evidence_id, command, principal, self._property_workflow(), plan
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
        domain_agent, capability = (
            ("LPA", "extract_permit_fields")
            if command.document_type == "PERMIT"
            else ("CLA", "extract_contract_clauses")
        )
        plans = tuple(
            self._runtime.prepare(
                AgentRunRequest(
                    agent_id=agent_id,
                    capability=agent_capability,
                    input_references=[f"legal-document:{command.document_version_id}"],
                    requested_tools=tools,
                    correlation_id=correlation_id,
                    idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
                )
            )
            for agent_id, agent_capability, tools in (
                ("DIA", "extract_structured_fields", ["alos.document.read"]),
                (domain_agent, capability, ["alos.legal.read"]),
                ("CEA", "check_completeness", ["alos.evidence.read"]),
            )
        )
        return self._store.submit_legal_document(
            command,
            principal,
            self._legal_workflow(),
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
        plans = tuple(
            self._runtime.prepare(
                AgentRunRequest(
                    agent_id=agent_id,
                    capability=capability,
                    input_references=[f"recruitment-request:{idempotency_key}"],
                    requested_tools=tools,
                    correlation_id=correlation_id,
                    idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
                )
            )
            for agent_id, capability, tools in (
                ("SEA", "compose_work_plan", ["alos.sop.read"]),
                (
                    "HRA",
                    "screen_administrative_requirements",
                    ["alos.hr.restricted_read"],
                ),
            )
        )
        return self._store.submit_recruitment_request(
            command,
            principal,
            self._hr_workflow(),
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
            plan = self._runtime.prepare(
                AgentRunRequest(
                    agent_id="HPA",
                    capability="check_personnel_file_completeness",
                    input_references=[f"recruitment-request:{recruitment_request_id}"],
                    requested_tools=["alos.hr.restricted_read"],
                    correlation_id=uuid4(),
                    idempotency_key=f"hpa-{idempotency_key}",
                )
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
        plans = tuple(
            self._runtime.prepare(
                AgentRunRequest(
                    agent_id=agent_id,
                    capability=capability,
                    input_references=[
                        f"executive-period:{command.period_start}:{command.period_end}"
                    ],
                    requested_tools=tools,
                    correlation_id=correlation_id,
                    idempotency_key=f"{agent_id.lower()}-{idempotency_key}",
                )
            )
            for agent_id, capability, tools in (
                (
                    "KDA",
                    "calculate_kpi_deterministically",
                    ["alos.verified_data.read", "deterministic.calculator"],
                ),
                ("CRA", "monitor_capa_deadline", ["alos.audit.read"]),
                ("ARA", "schedule_escalation", ["alos.policy.read"]),
                ("MCA", "aggregate_verified_facts", ["alos.executive.read"]),
            )
        )
        return self._store.generate_executive_brief(
            command,
            principal,
            self._executive_workflow(),
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
        require_division_role(principal, "SALES_MARKETING", Role.SALES)
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
        require_division_role(principal, "SALES_MARKETING", Role.SALES)
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

    def _payment_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-002")

    def _property_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-003")

    def _legal_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-004")

    def _hr_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-005")

    def _executive_workflow(self) -> WorkflowDefinition:
        return next(item for item in self._workflows.load_all() if item.workflow_id == "FLOW-006")
