import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Engine, create_engine, text

from alos.agents.contract import AgentDefinition
from alos.agents.runtime import AgentExecutionPlan
from alos.audit import compute_audit_entry_hash
from alos.config import default_repository_root
from alos.governance.approval_policy import (
    PaymentApprovalPolicy,
    PaymentApprovalPolicyRegistry,
)
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
    PaymentCancelCreate,
    PaymentDecisionCreate,
    PaymentRecordCreate,
    PaymentRequestCreate,
    PaymentRequestView,
    PaymentRevisionCreate,
    ProjectCreate,
    ProjectStatusUpdate,
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
    WorkItemStatus,
    WorkItemView,
)
from alos.security import Principal, Role, UserCreate, UserView
from alos.security.authorization import AuthorizationDenied
from alos.workflow.models import WorkflowDefinition
from alos.workflow.state_machine import StateMachine


class AgentReleaseConflictError(RuntimeError):
    """Raised when an immutable agent version is reused with different content."""


class WorkflowReleaseConflictError(RuntimeError):
    """Raised when an immutable workflow version is reused with different content."""


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url, pool_pre_ping=True)


class PostgresOperationalStore:
    def __init__(
        self,
        database: Database,
        payment_approval_policy: PaymentApprovalPolicy | None = None,
    ) -> None:
        self._engine = database.engine
        self._payment_approval_policy = payment_approval_policy or PaymentApprovalPolicyRegistry(
            default_repository_root() / "definitions"
        ).load()

    @staticmethod
    def _request_hash(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            default=str,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _load_command_receipt(
        cls,
        connection: Any,
        principal: Principal,
        operation: str,
        idempotency_key: str,
        request_payload: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        # Serialize commands that use the same organization/operation/key tuple.
        # Without this transaction-scoped lock, two concurrent first requests can
        # both miss the receipt and one of them would fail on the unique constraint
        # after performing the business mutation.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {
                "lock_key": (
                    f"{principal.organization_id}:{operation}:{idempotency_key}"
                )
            },
        )
        row = (
            connection.execute(
                text("""
                    SELECT request_hash, response_payload
                    FROM platform.command_receipts
                    WHERE organization_id = :organization_id
                      AND operation = :operation
                      AND idempotency_key = :idempotency_key
                """),
                {
                    "organization_id": principal.organization_id,
                    "operation": operation,
                    "idempotency_key": idempotency_key,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["request_hash"] != cls._request_hash(request_payload):
            raise ValueError("Idempotency-Key telah digunakan dengan payload berbeda")
        return cast(Mapping[str, Any], row["response_payload"])

    @classmethod
    def _save_command_receipt(
        cls,
        connection: Any,
        principal: Principal,
        operation: str,
        idempotency_key: str,
        request_payload: Mapping[str, Any],
        entity_type: str,
        entity_id: UUID,
        response_payload: Mapping[str, Any],
    ) -> None:
        connection.execute(
            text("""
                INSERT INTO platform.command_receipts
                    (organization_id, operation, idempotency_key, request_hash,
                     entity_type, entity_id, response_payload)
                VALUES (:organization_id, :operation, :idempotency_key, :request_hash,
                        :entity_type, :entity_id, CAST(:response_payload AS jsonb))
            """),
            {
                "organization_id": principal.organization_id,
                "operation": operation,
                "idempotency_key": idempotency_key,
                "request_hash": cls._request_hash(request_payload),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "response_payload": json.dumps(response_payload, default=str),
            },
        )

    def create_user(self, command: UserCreate, principal: Principal) -> UserView:
        user_id = uuid4()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            division_id = None
            if command.division_code is not None:
                division_id = connection.execute(
                    text(
                        """
                        SELECT division_id FROM identity.divisions
                        WHERE organization_id = :organization_id AND code = :division_code
                        """
                    ),
                    {
                        "organization_id": principal.organization_id,
                        "division_code": command.division_code,
                    },
                ).scalar_one_or_none()
                if division_id is None:
                    raise KeyError("Divisi tidak ditemukan pada organisasi pengguna")
            connection.execute(
                text(
                    """
                    INSERT INTO identity.users
                        (user_id, organization_id, email, display_name, status,
                         created_at, updated_at)
                    VALUES (:user_id, :organization_id, :email, :display_name,
                            'ACTIVE', :now, :now)
                    """
                ),
                {
                    "user_id": user_id,
                    "organization_id": principal.organization_id,
                    "email": command.email.lower(),
                    "display_name": command.display_name,
                    "now": now,
                },
            )

            connection.execute(
                text(
                    """
                    INSERT INTO identity.role_assignments
                        (user_id, division_id, role_code, reason, created_by, created_at)
                    VALUES (:user_id, :division_id, :role_code, 'Pembuatan pengguna awal',
                            (
                                SELECT user_id FROM identity.users
                                WHERE user_id = :created_by
                                  AND organization_id = :organization_id
                            ), :now)
                    """
                ),
                {
                    "user_id": user_id,
                    "division_id": division_id,
                    "role_code": command.role.value,
                    "created_by": principal.user_id,
                    "organization_id": principal.organization_id,
                    "now": now,
                },
            )
            result = UserView(
                user_id=user_id,
                email=command.email.lower(),
                display_name=command.display_name,
                status="ACTIVE",
                division_code=command.division_code,
                role=command.role,
                created_at=now,
            )
            self._append_audit(
                connection,
                principal,
                "identity.user_created",
                "user",
                user_id,
                user_id,
                None,
                result.model_dump(mode="json"),
            )
        return result

    def record_standalone_agent_run(
        self,
        plan: AgentExecutionPlan,
        principal: Principal,
        project_id: UUID | None,
    ) -> None:
        execution = plan.execution
        if execution is None:
            raise ValueError("Standalone agent run wajib sudah dieksekusi")
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            release_id = self._upsert_agent_release(connection, plan)
            connection.execute(
                text(
                    """
                    INSERT INTO agents.agent_runs
                        (agent_run_id, agent_release_id, organization_id, project_id,
                         status, input_reference, output_reference, correlation_id,
                         idempotency_key, started_at, completed_at, capability,
                         capability_version, capability_contract_digest,
                         execution_mode, approved_tools, contract_digest, handler_id,
                         evidence_references, warnings, verification_status, provider_metadata)
                    VALUES
                        (:agent_run_id, :agent_release_id, :organization_id, :project_id,
                         :status, CAST(:input_reference AS jsonb),
                         CAST(:output_reference AS jsonb), :correlation_id,
                         :idempotency_key, :occurred_at, :occurred_at, :capability,
                         :capability_version, :capability_contract_digest,
                         :execution_mode, CAST(:approved_tools AS jsonb), :contract_digest,
                         :handler_id, CAST(:evidence_references AS jsonb),
                         CAST(:warnings AS jsonb), :verification_status,
                         CAST(:provider_metadata AS jsonb))
                    """
                ),
                {
                    "agent_run_id": plan.run_id,
                    "agent_release_id": release_id,
                    "organization_id": principal.organization_id,
                    "project_id": project_id,
                    "status": execution.status.value,
                    "input_reference": json.dumps(plan.input_references),
                    "output_reference": json.dumps(
                        {
                            "_runtime": {
                                "handler_id": execution.handler_id,
                                "result": execution.output_reference,
                                "verification_status": execution.verification_status.value,
                            },
                            "production_effect": False,
                        }
                    ),
                    "correlation_id": plan.correlation_id,
                    "idempotency_key": plan.idempotency_key,
                    "occurred_at": now,
                    "capability": plan.capability,
                    "capability_version": plan.capability_version,
                    "capability_contract_digest": plan.capability_contract_digest,
                    "execution_mode": plan.execution_mode.value,
                    "approved_tools": json.dumps(
                        [item.model_dump(mode="json") for item in plan.approved_tool_releases]
                    ),
                    "contract_digest": plan.contract_digest,
                    "handler_id": execution.handler_id,
                    "evidence_references": json.dumps(execution.evidence_references),
                    "warnings": json.dumps(execution.warnings),
                    "verification_status": execution.verification_status.value,
                    "provider_metadata": json.dumps(execution.provider_metadata),
                },
            )
            self._append_audit(
                connection,
                principal,
                "agent.capability_evaluated",
                "agent_run",
                plan.run_id,
                plan.correlation_id,
                None,
                {
                    "agent_id": plan.agent_id,
                    "capability": plan.capability,
                    "status": execution.status.value,
                    "production_effect": False,
                },
            )

    def record_agent_lifecycle_transition(
        self,
        before: AgentDefinition,
        after: AgentDefinition,
        principal: Principal,
        action: str,
        reason: str,
        correlation_id: UUID,
    ) -> None:
        """Append an immutable audit entry for a human lifecycle operation."""

        entity_id = uuid5(NAMESPACE_URL, f"alos-agent:{after.agent_id}:{after.version}")
        with self._engine.begin() as connection:
            self._append_audit(
                connection,
                principal,
                action,
                "agent_contract",
                entity_id,
                correlation_id,
                before.model_dump(mode="json"),
                after.model_dump(mode="json"),
                reason,
            )

    def create_document(self, command: DocumentCreate, principal: Principal) -> DocumentView:
        document_id, version_id = uuid4(), uuid4()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            if command.project_id:
                self._assert_project(connection, command.project_id, principal)
            connection.execute(
                text(
                    """
                    INSERT INTO platform.documents
                        (document_id, organization_id, project_id, logical_name, classification,
                         created_at, created_by, updated_at)
                    VALUES (:document_id, :organization_id, :project_id, :logical_name,
                            :classification, :now, :created_by, :now)
                    """
                ),
                {
                    "document_id": document_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "logical_name": command.logical_name,
                    "classification": command.classification,
                    "now": now,
                    "created_by": principal.user_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO platform.document_versions
                        (document_version_id, document_id, version_number, object_key, sha256,
                         media_type, size_bytes, verification_status, created_at, created_by)
                    VALUES (:version_id, :document_id, 1, :object_key, :sha256, :media_type,
                            :size_bytes, 'UNVERIFIED', :now, :created_by)
                    """
                ),
                {
                    "version_id": version_id,
                    "document_id": document_id,
                    "object_key": command.object_key,
                    "sha256": command.sha256.lower(),
                    "media_type": command.media_type,
                    "size_bytes": command.size_bytes,
                    "now": now,
                    "created_by": principal.user_id,
                },
            )
            self._append_audit(
                connection,
                principal,
                "document.created",
                "document",
                document_id,
                document_id,
                None,
                command.model_dump(mode="json"),
            )
        return DocumentView(
            **command.model_dump(),
            document_id=document_id,
            document_version_id=version_id,
            organization_id=principal.organization_id,
            version_number=1,
            verification_status="UNVERIFIED",
            created_at=now,
        )

    def create_evidence(self, command: EvidenceCreate, principal: Principal) -> EvidenceView:
        evidence_id, now = uuid4(), datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text("""
                    SELECT wi.work_item_id, wi.organization_id, wi.project_id,
                           dv.document_version_id
                    FROM platform.work_items wi
                    JOIN platform.document_versions dv
                      ON dv.document_version_id = :document_version_id
                    JOIN platform.documents d ON d.document_id = dv.document_id
                    WHERE wi.work_item_id = :work_item_id
                      AND wi.organization_id = :organization_id
                      AND d.organization_id = wi.organization_id
                      AND (d.project_id IS NULL OR d.project_id = wi.project_id)
                      AND (d.division_id IS NULL OR d.division_id = wi.division_id)
                """),
                    {
                        "work_item_id": command.work_item_id,
                        "document_version_id": command.document_version_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Work item atau versi dokumen tidak ditemukan")
            if row["project_id"] is not None and not principal.can_access_project(
                row["project_id"]
            ):
                raise AuthorizationDenied("Pengguna tidak memiliki akses ke evidence")
            connection.execute(
                text("""
                INSERT INTO platform.evidence
                    (evidence_id, work_item_id, document_version_id, claim_type,
                     status, created_at, created_by)
                VALUES (:evidence_id, :work_item_id, :document_version_id, :claim_type,
                        'SUBMITTED', :now, :created_by)
            """),
                {
                    "evidence_id": evidence_id,
                    "work_item_id": command.work_item_id,
                    "document_version_id": command.document_version_id,
                    "claim_type": command.claim_type,
                    "now": now,
                    "created_by": principal.user_id,
                },
            )
            self._append_audit(
                connection,
                principal,
                "evidence.submitted",
                "evidence",
                evidence_id,
                evidence_id,
                None,
                command.model_dump(mode="json"),
            )
        return EvidenceView(
            evidence_id=evidence_id, **command.model_dump(), status="SUBMITTED", created_at=now
        )

    def request_approval(
        self, command: ApprovalRequestCreate, principal: Principal
    ) -> ApprovalRequestView:
        approval_id, now = uuid4(), datetime.now(UTC)
        if command.due_at is not None and command.due_at <= now:
            raise ValueError("Deadline approval wajib berada di masa depan")
        with self._engine.begin() as connection:
            self._assert_work_item(connection, command.work_item_id, principal)
            connection.execute(
                text("""
                INSERT INTO governance.approval_requests
                    (approval_request_id, work_item_id, requester_user_id, policy_code,
                     policy_version, status, material_fingerprint, due_at, created_at)
                VALUES (:approval_id, :work_item_id, :requester, :policy_code, '0.1.0',
                        'PENDING', :fingerprint, :due_at, :now)
            """),
                {
                    "approval_id": approval_id,
                    "work_item_id": command.work_item_id,
                    "requester": principal.user_id,
                    "policy_code": command.policy_code,
                    "fingerprint": command.material_fingerprint.lower(),
                    "due_at": command.due_at,
                    "now": now,
                },
            )
            self._append_audit(
                connection,
                principal,
                "approval.requested",
                "approval_request",
                approval_id,
                approval_id,
                None,
                command.model_dump(mode="json"),
            )
        return ApprovalRequestView(
            approval_request_id=approval_id,
            work_item_id=command.work_item_id,
            requester_user_id=principal.user_id,
            policy_code=command.policy_code,
            policy_version="0.1.0",
            status="PENDING",
            material_fingerprint=command.material_fingerprint.lower(),
            created_at=now,
            decided_at=None,
        )

    def decide_approval(
        self, approval_request_id: UUID, command: ApprovalDecisionCreate, principal: Principal
    ) -> ApprovalRequestView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text("""
                SELECT ar.approval_request_id, ar.work_item_id, ar.requester_user_id,
                       ar.policy_code, ar.policy_version, ar.status, ar.material_fingerprint,
                       ar.created_at, ar.decided_at, ar.assigned_approver_user_id
                FROM governance.approval_requests ar
                JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
                WHERE ar.approval_request_id = :approval_id
                  AND wi.organization_id = :organization_id
                FOR UPDATE OF ar
            """),
                    {
                        "approval_id": approval_request_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Approval request tidak ditemukan")
            if row["requester_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pemohon tidak dapat menyetujui permintaannya sendiri")
            if row["assigned_approver_user_id"] not in {None, principal.user_id}:
                raise AuthorizationDenied("Approval telah ditugaskan kepada approver lain")
            if row["status"] != "PENDING":
                raise ValueError("Approval request sudah diputuskan")
            self._assert_work_item(connection, row["work_item_id"], principal)
            connection.execute(
                text("""
                INSERT INTO governance.approval_decisions
                    (approval_request_id, approver_user_id, decision, reason, decided_at)
                VALUES (:approval_id, :approver, :decision, :reason, :now)
            """),
                {
                    "approval_id": approval_request_id,
                    "approver": principal.user_id,
                    "decision": command.decision,
                    "reason": command.reason,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                UPDATE governance.approval_requests SET status = :status, decided_at = :now
                WHERE approval_request_id = :approval_id
            """),
                {
                    "status": command.decision,
                    "now": now,
                    "approval_id": approval_request_id,
                },
            )
            connection.execute(
                text("""
                UPDATE platform.reminders SET status = 'CANCELLED'
                WHERE approval_request_id = :approval_id AND status = 'PENDING'
            """),
                {"approval_id": approval_request_id},
            )
            self._append_audit(
                connection,
                principal,
                "approval.decided",
                "approval_request",
                approval_request_id,
                approval_request_id,
                dict(row),
                command.model_dump(),
            )
            updated = dict(row)
            updated["status"] = command.decision
            updated["decided_at"] = now
            return ApprovalRequestView(**updated)

    def create_exception(self, command: ExceptionCreate, principal: Principal) -> ExceptionView:
        exception_id, now = uuid4(), datetime.now(UTC)
        with self._engine.begin() as connection:
            if command.work_item_id:
                self._assert_work_item(connection, command.work_item_id, principal)
            connection.execute(
                text("""
                INSERT INTO governance.exceptions
                    (exception_id, organization_id, work_item_id, category, severity, status,
                     owner_user_id, due_at, created_at)
                VALUES (:exception_id, :organization_id, :work_item_id, :category, :severity,
                        'OPEN', :owner, :due_at, :now)
            """),
                {
                    "exception_id": exception_id,
                    "organization_id": principal.organization_id,
                    "work_item_id": command.work_item_id,
                    "category": command.category,
                    "severity": command.severity,
                    "owner": principal.user_id,
                    "due_at": command.due_at,
                    "now": now,
                },
            )
            self._append_audit(
                connection,
                principal,
                "exception.created",
                "exception",
                exception_id,
                exception_id,
                None,
                command.model_dump(mode="json"),
            )
        return ExceptionView(
            exception_id=exception_id,
            **command.model_dump(),
            status="OPEN",
            owner_user_id=principal.user_id,
            created_at=now,
        )

    def create_capa(self, command: CapaCreate, principal: Principal) -> CapaView:
        capa_id, now = uuid4(), datetime.now(UTC)
        with self._engine.begin() as connection:
            exists = (
                connection.execute(
                    text("""
                SELECT e.exception_id, e.work_item_id, wi.project_id
                FROM governance.exceptions e
                LEFT JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
                WHERE e.exception_id = :id
                  AND e.organization_id = :organization_id
            """),
                    {"id": command.exception_id, "organization_id": principal.organization_id},
                )
                .mappings()
                .one_or_none()
            )
            if exists is None:
                raise KeyError("Exception tidak ditemukan")
            if exists["work_item_id"] is not None:
                self._assert_work_item(connection, exists["work_item_id"], principal)
            if exists["project_id"] is not None and not principal.can_access_project(
                exists["project_id"]
            ):
                raise AuthorizationDenied("Pengguna tidak memiliki akses ke CAPA")
            connection.execute(
                text("""
                INSERT INTO governance.capas
                    (capa_id, exception_id, status, root_cause, corrective_action,
                     preventive_action, due_at, created_at)
                VALUES (:capa_id, :exception_id, 'OPEN', :root_cause, :corrective_action,
                        :preventive_action, :due_at, :now)
            """),
                {
                    "capa_id": capa_id,
                    "exception_id": command.exception_id,
                    "root_cause": command.root_cause,
                    "corrective_action": command.corrective_action,
                    "preventive_action": command.preventive_action,
                    "due_at": command.due_at,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                    UPDATE governance.exceptions
                    SET status = 'CAPA_REQUIRED' WHERE exception_id = :id
                """),
                {"id": command.exception_id},
            )
            self._append_audit(
                connection,
                principal,
                "capa.created",
                "capa",
                capa_id,
                capa_id,
                None,
                command.model_dump(mode="json"),
            )
        return CapaView(
            capa_id=capa_id,
            status="OPEN",
            reviewer_user_id=None,
            closed_at=None,
            created_at=now,
            **command.model_dump(),
        )

    def create_budget(self, command: BudgetCreate, principal: Principal) -> BudgetView:
        budget_id, now = uuid4(), datetime.now(UTC)
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            connection.execute(
                text("""
                INSERT INTO finance.budgets
                    (budget_id, organization_id, project_id, code, name, currency,
                     allocated_amount, status, created_at, created_by, updated_at)
                VALUES (:budget_id, :organization_id, :project_id, :code, :name,
                        :currency, :amount, 'ACTIVE', :now, :actor, :now)
            """),
                {
                    "budget_id": budget_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "code": command.code,
                    "name": command.name,
                    "currency": command.currency,
                    "amount": command.allocated_amount,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            self._append_audit(
                connection,
                principal,
                "finance.budget_created",
                "budget",
                budget_id,
                budget_id,
                None,
                command.model_dump(mode="json"),
            )
        return BudgetView(
            budget_id=budget_id,
            committed_amount=Decimal("0"),
            spent_amount=Decimal("0"),
            available_amount=command.allocated_amount,
            status="ACTIVE",
            created_at=now,
            **command.model_dump(),
        )

    def prepare_payment_request(
        self, command: PaymentRequestCreate, principal: Principal
    ) -> dict[str, object]:
        document_ids = {command.document_version_id, *command.supporting_document_version_ids}
        with self._engine.connect() as connection:
            self._assert_project(connection, command.project_id, principal)
            budget = (
                connection.execute(
                    text("""
                        SELECT currency, allocated_amount, committed_amount, spent_amount
                        FROM finance.budgets
                        WHERE budget_id = :budget_id AND project_id = :project_id
                          AND organization_id = :organization_id AND status = 'ACTIVE'
                    """),
                    {
                        "budget_id": command.budget_id,
                        "project_id": command.project_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if budget is None:
                raise KeyError("Budget aktif tidak ditemukan")
            if budget["currency"] != command.currency:
                raise ValueError("Mata uang payment request berbeda dengan budget")
            found_documents = connection.execute(
                text("""
                    SELECT dv.document_version_id
                    FROM platform.document_versions dv
                    JOIN platform.documents d ON d.document_id = dv.document_id
                    WHERE dv.document_version_id = ANY(CAST(:version_ids AS uuid[]))
                      AND d.organization_id = :organization_id
                      AND (d.project_id IS NULL OR d.project_id = :project_id)
                      AND (
                          d.division_id IS NULL
                          OR d.division_id = (
                              SELECT division_id FROM identity.divisions
                              WHERE organization_id = :organization_id AND code = 'FINANCE'
                          )
                      )
                      AND dv.verification_status <> 'REJECTED'
                      AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
                """),
                {
                    "version_ids": list(document_ids),
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                },
            ).scalars()
            found_ids = set(found_documents)
            if found_ids != document_ids:
                raise KeyError("Dokumen payment request tidak lengkap atau di luar project")
            available = (
                budget["allocated_amount"]
                - budget["committed_amount"]
                - budget["spent_amount"]
            )
        required_items = ["PRIMARY_DOCUMENT"]
        if command.category_code in {"TAX", "CONTRACTOR"}:
            required_items.append("SUPPORTING_DOCUMENT")
        provided_items = ["PRIMARY_DOCUMENT"]
        if command.supporting_document_version_ids:
            provided_items.append("SUPPORTING_DOCUMENT")
        return {
            "available_amount": str(available),
            "document_metadata_valid": True,
            "document_version_count": len(found_ids),
            "required_items": required_items,
            "provided_items": provided_items,
            "evidence_complete": set(required_items).issubset(provided_items),
        }

    def document_execution_context(
        self,
        document_version_id: UUID,
        project_id: UUID,
        principal: Principal,
    ) -> dict[str, object]:
        """Load trusted document metadata before dispatching an agent capability."""

        with self._engine.connect() as connection:
            self._assert_project(connection, project_id, principal)
            row = (
                connection.execute(
                    text(
                        """
                        SELECT dv.sha256, dv.scan_status, dv.verification_status
                        FROM platform.document_versions dv
                        JOIN platform.documents d ON d.document_id = dv.document_id
                        WHERE dv.document_version_id = :document_version_id
                          AND d.organization_id = :organization_id
                          AND (d.project_id IS NULL OR d.project_id = :project_id)
                        """
                    ),
                    {
                        "document_version_id": document_version_id,
                        "organization_id": principal.organization_id,
                        "project_id": project_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError("Versi dokumen tidak ditemukan pada project dan organisasi")
        scan_status = str(row["scan_status"])
        if scan_status not in {"NOT_CONFIGURED", "CLEAN"}:
            raise ValueError("Dokumen belum lulus pemeriksaan keamanan")
        sha256 = str(row["sha256"]).lower()
        checksum_valid = len(sha256) == 64 and all(
            character in "0123456789abcdef" for character in sha256
        )
        if not checksum_valid:
            raise ValueError("Checksum dokumen tidak valid")
        return {
            "checksum_valid": True,
            "scan_status": scan_status,
            "document_verification_status": str(row["verification_status"]),
        }

    def create_payment_request(
        self,
        command: PaymentRequestCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> PaymentRequestView:
        payment_request_id, work_item_id, workflow_run_id = uuid4(), uuid4(), uuid4()
        now = datetime.now(UTC)
        approval_id: UUID | None = None
        machine = StateMachine(definition)
        operation = "finance.payment_request.create"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return PaymentRequestView.model_validate(receipt)
            actor_exists = connection.execute(
                text("""
                    SELECT 1 FROM identity.users
                    WHERE user_id = :id AND organization_id = :organization_id
                      AND status = 'ACTIVE'
                """),
                {"id": principal.user_id, "organization_id": principal.organization_id},
            ).first()
            if actor_exists is None:
                raise AuthorizationDenied("Pengguna pemohon belum diprovisikan")
            budget = (
                connection.execute(
                    text("""
                SELECT budget_id, currency, allocated_amount, committed_amount, spent_amount
                FROM finance.budgets
                WHERE budget_id = :budget_id AND project_id = :project_id
                  AND organization_id = :organization_id AND status = 'ACTIVE'
                FOR UPDATE
            """),
                    {
                        "budget_id": command.budget_id,
                        "project_id": command.project_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if budget is None:
                raise KeyError("Budget aktif tidak ditemukan")
            document_ids = {
                command.document_version_id,
                *command.supporting_document_version_ids,
            }
            found_documents = set(
                connection.execute(
                text("""
                SELECT dv.document_version_id FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = ANY(CAST(:version_ids AS uuid[]))
                  AND d.organization_id = :organization_id
                  AND (d.project_id IS NULL OR d.project_id = :project_id)
                  AND (
                      d.division_id IS NULL
                      OR d.division_id = (
                          SELECT division_id FROM identity.divisions
                          WHERE organization_id = :organization_id AND code = 'FINANCE'
                      )
                  )
                  AND dv.verification_status <> 'REJECTED'
                  AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
            """),
                {
                    "version_ids": list(document_ids),
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                },
                ).scalars()
            )
            if found_documents != document_ids:
                raise KeyError("Dokumen payment request tidak lengkap atau di luar project")
            if budget["currency"] != command.currency:
                raise ValueError("Mata uang payment request berbeda dengan budget")
            available_amount = (
                budget["allocated_amount"] - budget["committed_amount"] - budget["spent_amount"]
            )
            budget_available = available_amount >= command.amount
            evidence_complete = (
                command.category_code not in {"TAX", "CONTRACTOR"}
                or bool(command.supporting_document_version_ids)
            )
            approval_route, required_role, approval_sla_hours = self._payment_approval_route(
                command.amount
            )
            division_id = connection.execute(
                text("""
                SELECT division_id FROM identity.divisions
                WHERE organization_id = :organization_id AND code = 'FINANCE'
            """),
                {"organization_id": principal.organization_id},
            ).scalar_one()
            connection.execute(
                text("""
                INSERT INTO platform.work_items
                    (work_item_id, organization_id, project_id, division_id, title,
                     work_type, priority, status, correlation_id, created_at,
                     created_by, updated_at)
                VALUES (:work_item_id, :organization_id, :project_id, :division_id,
                        :title, 'PAYMENT_REQUEST', 'HIGH', :status, :correlation_id,
                        :now, :actor, :now)
            """),
                {
                    "work_item_id": work_item_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "division_id": division_id,
                    "title": f"Pembayaran: {command.payee_name}",
                    "status": (
                        "PENDING_APPROVAL"
                        if budget_available and evidence_complete
                        else "BLOCKED"
                    ),
                    "correlation_id": correlation_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text("""
                INSERT INTO workflow.workflow_runs
                    (workflow_run_id, workflow_release_id, work_item_id, current_step,
                     status, correlation_id, idempotency_key, started_at)
                VALUES (:run_id, :release_id, :work_item_id, 'request-submitted',
                        'ACTIVE', :correlation_id, :idempotency_key, :now)
            """),
                {
                    "run_id": workflow_run_id,
                    "release_id": release_id,
                    "work_item_id": work_item_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            fingerprint = hashlib.sha256(
                json.dumps(
                    command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            connection.execute(
                text("""
                INSERT INTO finance.payment_requests
                    (payment_request_id, organization_id, project_id, budget_id,
                     work_item_id, workflow_run_id, document_version_id, requester_user_id,
                     payee_name, vendor_reference, category_code, purpose, amount, currency,
                     requested_payment_date, status, budget_available, evidence_complete,
                     approval_route, material_fingerprint, created_at, updated_at)
                VALUES (:payment_request_id, :organization_id, :project_id, :budget_id,
                        :work_item_id, :workflow_run_id, :document_version_id, :requester,
                        :payee_name, :vendor_reference, :category_code, :purpose, :amount,
                        :currency, :payment_date, :status, :available, :evidence_complete,
                        :approval_route, :fingerprint, :now, :now)
            """),
                {
                    "payment_request_id": payment_request_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "budget_id": command.budget_id,
                    "work_item_id": work_item_id,
                    "workflow_run_id": workflow_run_id,
                    "document_version_id": command.document_version_id,
                    "requester": principal.user_id,
                    "payee_name": command.payee_name,
                    "vendor_reference": command.vendor_reference,
                    "category_code": command.category_code,
                    "purpose": command.purpose,
                    "amount": command.amount,
                    "currency": command.currency,
                    "payment_date": command.requested_payment_date,
                    "status": (
                        "PENDING_APPROVAL"
                        if budget_available and evidence_complete
                        else "EXCEPTION"
                    ),
                    "available": budget_available,
                    "evidence_complete": evidence_complete,
                    "approval_route": approval_route,
                    "fingerprint": fingerprint,
                    "now": now,
                },
            )
            for version_id in document_ids:
                connection.execute(
                    text("""
                    INSERT INTO platform.evidence
                        (evidence_id, work_item_id, document_version_id, claim_type,
                         status, created_at, created_by)
                    VALUES (:evidence_id, :work_item_id, :version_id, :claim_type,
                            'SUBMITTED', :now, :actor)
                """),
                    {
                        "evidence_id": uuid4(),
                        "work_item_id": work_item_id,
                        "version_id": version_id,
                        "claim_type": (
                            "PAYMENT_PRIMARY_DOCUMENT"
                            if version_id == command.document_version_id
                            else "PAYMENT_SUPPORTING_DOCUMENT"
                        ),
                        "now": now,
                        "actor": principal.user_id,
                    },
                )
            transitions = [
                machine.transition("request-submitted", "submitted"),
                machine.transition("document-extraction", "extracted"),
                machine.transition(
                    "evidence-check", "complete" if evidence_complete else "incomplete"
                ),
            ]
            current_step = transitions[-1].current_step
            if evidence_complete:
                budget_transition = machine.transition(
                    "budget-check", "available" if budget_available else "unavailable"
                )
                transitions.append(budget_transition)
                current_step = budget_transition.current_step
            if evidence_complete and budget_available:
                approval_id = uuid4()
                routed = machine.transition("approval-routing", "routed")
                transitions.append(routed)
                current_step = routed.current_step
                approval_due_at = now + timedelta(hours=approval_sla_hours)
                connection.execute(
                    text("""
                    INSERT INTO governance.approval_requests
                        (approval_request_id, work_item_id, requester_user_id, policy_code,
                         policy_version, status, material_fingerprint, due_at,
                         required_role_code, required_division_code, routing_rule,
                         created_at)
                    VALUES (:approval_id, :work_item_id, :requester, 'FINANCE_PAYMENT',
                            '1.0.0', 'PENDING', :fingerprint, :due_at, :required_role,
                            :required_division, :routing_rule, :now)
                """),
                    {
                        "approval_id": approval_id,
                        "work_item_id": work_item_id,
                        "requester": principal.user_id,
                        "fingerprint": fingerprint,
                        "due_at": approval_due_at,
                        "required_role": required_role,
                        "required_division": (
                            None if required_role == "DIRECTOR" else "FINANCE"
                        ),
                        "routing_rule": approval_route,
                        "now": now,
                    },
                )
                connection.execute(
                    text("""
                    UPDATE finance.payment_requests SET approval_request_id = :approval_id
                    WHERE payment_request_id = :payment_request_id
                """),
                    {"approval_id": approval_id, "payment_request_id": payment_request_id},
                )
                connection.execute(
                    text("""
                    UPDATE finance.budgets SET committed_amount = committed_amount + :amount,
                        updated_at = :now, version = version + 1 WHERE budget_id = :budget_id
                """),
                    {"amount": command.amount, "now": now, "budget_id": command.budget_id},
                )
                connection.execute(
                    text("""
                    UPDATE platform.work_items SET due_at = :due_at, updated_at = :now
                    WHERE work_item_id = :work_item_id
                """),
                    {"due_at": approval_due_at, "now": now, "work_item_id": work_item_id},
                )
            else:
                approval_id = None
                exception_due_at = now + timedelta(hours=24)
                exception_category = (
                    "EVIDENCE_INCOMPLETE"
                    if not evidence_complete
                    else "BUDGET_INSUFFICIENT"
                )
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                        VALUES (:organization_id, :work_item_id, :category,
                            'HIGH', 'OPEN', :owner, :due_at, :now)
                """),
                    {
                        "organization_id": principal.organization_id,
                        "work_item_id": work_item_id,
                        "category": exception_category,
                        "owner": principal.user_id,
                        "due_at": exception_due_at,
                        "now": now,
                    },
                )
                connection.execute(
                    text("""
                        UPDATE platform.work_items
                        SET due_at = :due_at, owner_user_id = :owner, updated_at = :now
                        WHERE work_item_id = :work_item_id
                    """),
                    {
                        "due_at": exception_due_at,
                        "owner": principal.user_id,
                        "now": now,
                        "work_item_id": work_item_id,
                    },
                )
            agent_transitions = {"DIA": transitions[1], "CEA": transitions[2]}
            if evidence_complete:
                agent_transitions["BCA"] = transitions[3]
            if evidence_complete and budget_available:
                agent_transitions["ARA"] = transitions[4]
            for plan in plans:
                transition = agent_transitions.get(plan.agent_id)
                agent_run_id = self._record_agent_run(
                    connection,
                    plan,
                    workflow_run_id,
                    correlation_id,
                    {
                        "step": transition.current_step if transition else "NOT_REACHED",
                        "budget_available": budget_available,
                        "evidence_complete": evidence_complete,
                        "approval_route": approval_route,
                    },
                    now,
                )
                check_type = {
                    "DIA": "DOCUMENT",
                    "CEA": "EVIDENCE",
                    "BCA": "BUDGET",
                    "ARA": "APPROVAL_ROUTE",
                }.get(plan.agent_id)
                if check_type is not None:
                    passed = {
                        "DOCUMENT": True,
                        "EVIDENCE": evidence_complete,
                        "BUDGET": budget_available,
                        "APPROVAL_ROUTE": evidence_complete and budget_available,
                    }[check_type]
                    connection.execute(
                        text("""
                        INSERT INTO finance.payment_checks
                            (payment_request_id, revision_number, check_type, agent_id,
                             agent_run_id, status, details, checked_at)
                        VALUES (:payment_request_id, 0, :check_type, :agent_id,
                                :agent_run_id, :status, CAST(:details AS jsonb), :now)
                    """),
                        {
                            "payment_request_id": payment_request_id,
                            "check_type": check_type,
                            "agent_id": plan.agent_id,
                            "agent_run_id": agent_run_id,
                            "status": "PASSED" if passed else "FAILED",
                            "details": json.dumps(
                                {
                                    "budget_available": budget_available,
                                    "evidence_complete": evidence_complete,
                                    "approval_route": approval_route,
                                }
                            ),
                            "now": now,
                        },
                    )
            self._record_transition(
                connection,
                workflow_run_id,
                transitions[0],
                "HUMAN",
                principal.user_id,
                now,
            )
            for transition, agent_id in zip(
                transitions[1:], ("DIA", "CEA", "BCA", "ARA"), strict=False
            ):
                self._record_transition(
                    connection, workflow_run_id, transition, "AGENT", agent_id, now
                )
            terminal = current_step == "exception-open"
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = :step, status = :status,
                    completed_at = :completed_at, version = version + 1
                WHERE workflow_run_id = :run_id
            """),
                {
                    "step": current_step,
                    "status": "COMPLETED" if terminal else "ACTIVE",
                    "completed_at": now if terminal else None,
                    "run_id": workflow_run_id,
                },
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_requested",
                "payment_request",
                payment_request_id,
                correlation_id,
                None,
                {
                    "amount": str(command.amount),
                    "current_step": current_step,
                    "budget_available": budget_available,
                    "evidence_complete": evidence_complete,
                    "approval_route": approval_route,
                },
            )
            result = PaymentRequestView(
                payment_request_id=payment_request_id,
                work_item_id=work_item_id,
                workflow_run_id=workflow_run_id,
                approval_request_id=approval_id,
                project_id=command.project_id,
                budget_id=command.budget_id,
                payee_name=command.payee_name,
                vendor_reference=command.vendor_reference,
                category_code=command.category_code,
                purpose=command.purpose,
                amount=command.amount,
                currency=command.currency,
                requested_payment_date=command.requested_payment_date,
                status=(
                    "PENDING_APPROVAL"
                    if budget_available and evidence_complete
                    else "EXCEPTION"
                ),
                current_step=current_step,
                budget_available=budget_available,
                evidence_complete=evidence_complete,
                approval_route=approval_route,
                correlation_id=correlation_id,
                created_at=now,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
        return result

    def decide_payment(
        self,
        payment_request_id: UUID,
        command: PaymentDecisionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        operation = f"finance.payment_request.decision:{payment_request_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            if context["requester_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pemohon tidak dapat menyetujui pembayarannya sendiri")
            self._assert_payment_approver(context, principal)
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return FinanceWorkflowResult.model_validate(receipt)
            if context["current_step"] != "finance-approval":
                raise ValueError("Payment request tidak menunggu approval Finance")
            outcome = {
                "APPROVED": "approved",
                "REJECTED": "rejected",
                "REVISION_REQUESTED": "revision_requested",
            }[command.decision]
            transition = machine.transition("finance-approval", outcome)
            terminal = transition.terminal
            connection.execute(
                text("""
                INSERT INTO governance.approval_decisions
                    (approval_request_id, approver_user_id, decision, reason, decided_at)
                VALUES (:approval_id, :approver, :decision, :reason, :now)
            """),
                {
                    "approval_id": context["approval_request_id"],
                    "approver": principal.user_id,
                    "decision": command.decision,
                    "reason": command.reason,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                UPDATE governance.approval_requests SET status = :status, decided_at = :now
                WHERE approval_request_id = :approval_id AND status = 'PENDING'
            """),
                {
                    "status": command.decision,
                    "now": now,
                    "approval_id": context["approval_request_id"],
                },
            )
            work_status = {
                "APPROVED": "IN_PROGRESS",
                "REJECTED": "BLOCKED",
                "REVISION_REQUESTED": "NEEDS_REVIEW",
            }[command.decision]
            if command.decision != "APPROVED":
                connection.execute(
                    text("""
                    UPDATE finance.budgets SET committed_amount = committed_amount - :amount,
                        updated_at = :now, version = version + 1 WHERE budget_id = :budget_id
                """),
                    {"amount": context["amount"], "now": now, "budget_id": context["budget_id"]},
                )
                if command.decision == "REJECTED":
                    exception_due_at = now + timedelta(hours=24)
                    connection.execute(
                        text("""
                        INSERT INTO governance.exceptions
                            (organization_id, work_item_id, category, severity, status,
                             owner_user_id, due_at, created_at)
                        VALUES (:organization_id, :work_item_id, 'PAYMENT_REJECTED',
                                'MEDIUM', 'OPEN', :owner, :due_at, :now)
                    """),
                        {
                            "work_item_id": context["work_item_id"],
                            "organization_id": principal.organization_id,
                            "owner": context["requester_user_id"],
                            "due_at": exception_due_at,
                            "now": now,
                        },
                    )
                    connection.execute(
                        text("""
                            UPDATE platform.work_items
                            SET owner_user_id = :owner, due_at = :due_at, updated_at = :now
                            WHERE work_item_id = :work_item_id
                        """),
                        {
                            "owner": context["requester_user_id"],
                            "due_at": exception_due_at,
                            "now": now,
                            "work_item_id": context["work_item_id"],
                        },
                    )
                else:
                    revision_due_at = now + timedelta(hours=48)
                    connection.execute(
                        text("""
                        UPDATE platform.work_items
                        SET owner_user_id = :owner, due_at = :due_at, updated_at = :now
                        WHERE work_item_id = :work_item_id
                    """),
                        {
                            "owner": context["requester_user_id"],
                            "due_at": revision_due_at,
                            "now": now,
                            "work_item_id": context["work_item_id"],
                        },
                    )
                    connection.execute(
                        text("""
                        INSERT INTO platform.reminders
                            (organization_id, work_item_id, recipient_user_id,
                             reminder_type, status, scheduled_for, created_at)
                        VALUES (:organization_id, :work_item_id, :recipient,
                                'DUE_SOON', 'PENDING', :scheduled_for, :now)
                        ON CONFLICT DO NOTHING
                    """),
                        {
                            "organization_id": principal.organization_id,
                            "work_item_id": context["work_item_id"],
                            "recipient": context["requester_user_id"],
                            "scheduled_for": revision_due_at,
                            "now": now,
                        },
                    )
            else:
                payment_action_due_at = datetime.combine(
                    context["requested_payment_date"], time.max, tzinfo=UTC
                )
                connection.execute(
                    text("""
                        UPDATE platform.work_items
                        SET due_at = :due_at, updated_at = :now
                        WHERE work_item_id = :work_item_id
                    """),
                    {
                        "due_at": payment_action_due_at,
                        "now": now,
                        "work_item_id": context["work_item_id"],
                    },
                )
            self._update_payment_state(
                connection,
                context,
                transition.current_step,
                command.decision,
                work_status,
                terminal,
                now,
            )
            self._record_transition(
                connection, context["workflow_run_id"], transition, "HUMAN", principal.user_id, now
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_decided",
                "payment_request",
                payment_request_id,
                context["correlation_id"],
                None,
                command.model_dump(),
            )
            result = self._finance_result(
                context, transition.current_step, command.decision, work_status, terminal
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
            return result

    def record_payment(
        self,
        payment_request_id: UUID,
        command: PaymentRecordCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        operation = f"finance.payment_request.payment:{payment_request_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return FinanceWorkflowResult.model_validate(receipt)
            if context["current_step"] != "payment-action" or context["status"] != "APPROVED":
                raise ValueError("Payment request belum disetujui")
            if command.amount != context["amount"]:
                raise ValueError("Jumlah pembayaran berbeda dari permintaan yang disetujui")
            if command.currency != context["currency"]:
                raise ValueError("Mata uang pembayaran berbeda dari permintaan yang disetujui")
            evidence = connection.execute(
                text("""
                SELECT 1 FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = :version_id
                  AND d.organization_id = :organization_id
                  AND (d.project_id IS NULL OR d.project_id = :project_id)
                  AND (
                      d.division_id IS NULL
                      OR d.division_id = (
                          SELECT division_id FROM identity.divisions
                          WHERE organization_id = :organization_id AND code = 'FINANCE'
                      )
                  )
                  AND dv.verification_status <> 'REJECTED'
                  AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
            """),
                {
                    "version_id": command.evidence_document_version_id,
                    "organization_id": principal.organization_id,
                    "project_id": context["project_id"],
                },
            ).first()
            if evidence is None:
                raise KeyError("Evidence pembayaran tidak ditemukan")
            transition = machine.transition("payment-action", "recorded")
            connection.execute(
                text("""
                INSERT INTO finance.payment_records
                    (organization_id, payment_request_id, payment_reference, amount,
                     currency, paid_at,
                     evidence_document_version_id, recorded_by_user_id, idempotency_key,
                     created_at)
                VALUES (:organization_id, :payment_request_id, :reference, :amount,
                        :currency, :paid_at, :evidence, :actor, :idempotency_key, :now)
            """),
                {
                    "organization_id": principal.organization_id,
                    "payment_request_id": payment_request_id,
                    "reference": command.payment_reference,
                    "amount": command.amount,
                    "currency": command.currency,
                    "paid_at": command.paid_at,
                    "evidence": command.evidence_document_version_id,
                    "actor": principal.user_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO platform.evidence
                    (evidence_id, work_item_id, document_version_id, claim_type,
                     status, created_at, created_by)
                VALUES (:evidence_id, :work_item_id, :document_version_id,
                        'PAYMENT_PROOF', 'SUBMITTED', :now, :actor)
            """),
                {
                    "evidence_id": uuid4(),
                    "work_item_id": context["work_item_id"],
                    "document_version_id": command.evidence_document_version_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            self._update_payment_state(
                connection, context, transition.current_step, "PAID", "IN_PROGRESS", False, now
            )
            connection.execute(
                text("""
                    UPDATE platform.work_items
                    SET due_at = :due_at, updated_at = :now
                    WHERE work_item_id = :work_item_id
                """),
                {
                    "due_at": now + timedelta(hours=24),
                    "now": now,
                    "work_item_id": context["work_item_id"],
                },
            )
            self._record_transition(
                connection, context["workflow_run_id"], transition, "HUMAN", principal.user_id, now
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_recorded",
                "payment_request",
                payment_request_id,
                context["correlation_id"],
                None,
                command.model_dump(mode="json"),
            )
            result = self._finance_result(
                context, transition.current_step, "PAID", "IN_PROGRESS", False
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
            return result

    def cancel_payment(
        self,
        payment_request_id: UUID,
        command: PaymentCancelCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        operation = f"finance.payment_request.cancel:{payment_request_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            if context["requester_user_id"] != principal.user_id and not (
                principal.has_any_role(Role.DIRECTOR)
                or (
                    principal.has_any_role(Role.DIVISION_HEAD)
                    and "FINANCE" in principal.division_codes
                )
            ):
                raise AuthorizationDenied(
                    "Pembatalan hanya dapat dilakukan pemohon, Kepala Finance, atau Direktur"
                )
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return FinanceWorkflowResult.model_validate(receipt)
            if context["current_step"] not in {
                "finance-approval",
                "revision-required",
                "payment-action",
            }:
                raise ValueError("Payment request tidak dapat dibatalkan pada status ini")
            transition = machine.transition(context["current_step"], "cancelled")
            if context["status"] in {"PENDING_APPROVAL", "APPROVED"}:
                connection.execute(
                    text("""
                    UPDATE finance.budgets
                    SET committed_amount = committed_amount - :amount,
                        updated_at = :now, version = version + 1
                    WHERE budget_id = :budget_id
                """),
                    {
                        "amount": context["amount"],
                        "now": now,
                        "budget_id": context["budget_id"],
                    },
                )
            connection.execute(
                text("""
                UPDATE governance.approval_requests
                SET status = 'CANCELLED', decided_at = :now
                WHERE approval_request_id = :approval_id AND status = 'PENDING'
            """),
                {"approval_id": context["approval_request_id"], "now": now},
            )
            connection.execute(
                text("""
                UPDATE finance.payment_requests
                SET status = 'CANCELLED', cancelled_by_user_id = :actor,
                    cancelled_at = :now, cancellation_reason = :reason,
                    updated_at = :now, version = version + 1
                WHERE payment_request_id = :payment_request_id
            """),
                {
                    "actor": principal.user_id,
                    "now": now,
                    "reason": command.reason,
                    "payment_request_id": payment_request_id,
                },
            )
            connection.execute(
                text("""
                UPDATE platform.work_items
                SET status = 'CANCELLED', completed_at = :now, due_at = NULL,
                    updated_at = :now, version = version + 1
                WHERE work_item_id = :work_item_id
            """),
                {"now": now, "work_item_id": context["work_item_id"]},
            )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs
                SET current_step = :step, status = 'COMPLETED', completed_at = :now,
                    version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": transition.current_step,
                    "now": now,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            connection.execute(
                text("""
                UPDATE platform.reminders SET status = 'CANCELLED'
                WHERE work_item_id = :work_item_id AND status = 'PENDING'
            """),
                {"work_item_id": context["work_item_id"]},
            )
            self._record_transition(
                connection,
                context["workflow_run_id"],
                transition,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_cancelled",
                "payment_request",
                payment_request_id,
                context["correlation_id"],
                {"status": context["status"]},
                {"status": "CANCELLED"},
                command.reason,
            )
            result = self._finance_result(
                context,
                transition.current_step,
                "CANCELLED",
                "CANCELLED",
                True,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
            return result

    def revise_payment(
        self,
        payment_request_id: UUID,
        command: PaymentRevisionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        operation = f"finance.payment_request.revise:{payment_request_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            if context["requester_user_id"] != principal.user_id:
                raise AuthorizationDenied("Revisi hanya dapat diajukan pemohon semula")
            if command.project_id != context["project_id"]:
                raise ValueError("Project payment request tidak dapat diubah saat revisi")
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return FinanceWorkflowResult.model_validate(receipt)
            if context["current_step"] != "revision-required":
                raise ValueError("Payment request tidak menunggu revisi")
            budget = (
                connection.execute(
                    text("""
                    SELECT budget_id, currency, allocated_amount, committed_amount, spent_amount
                    FROM finance.budgets
                    WHERE budget_id = :budget_id AND project_id = :project_id
                      AND organization_id = :organization_id AND status = 'ACTIVE'
                    FOR UPDATE
                """),
                    {
                        "budget_id": command.budget_id,
                        "project_id": command.project_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if budget is None:
                raise KeyError("Budget aktif tidak ditemukan")
            if budget["currency"] != command.currency:
                raise ValueError("Mata uang payment request berbeda dengan budget")
            document_ids = {
                command.document_version_id,
                *command.supporting_document_version_ids,
            }
            found_documents = set(
                connection.execute(
                    text("""
                    SELECT dv.document_version_id
                    FROM platform.document_versions dv
                    JOIN platform.documents d ON d.document_id = dv.document_id
                    WHERE dv.document_version_id = ANY(CAST(:version_ids AS uuid[]))
                      AND d.organization_id = :organization_id
                      AND (d.project_id IS NULL OR d.project_id = :project_id)
                      AND (
                          d.division_id IS NULL
                          OR d.division_id = (
                              SELECT division_id FROM identity.divisions
                              WHERE organization_id = :organization_id AND code = 'FINANCE'
                          )
                      )
                      AND dv.verification_status <> 'REJECTED'
                      AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
                """),
                    {
                        "version_ids": list(document_ids),
                        "organization_id": principal.organization_id,
                        "project_id": command.project_id,
                    },
                ).scalars()
            )
            if found_documents != document_ids:
                raise KeyError("Dokumen revisi tidak lengkap atau di luar project")
            available_amount = (
                budget["allocated_amount"] - budget["committed_amount"] - budget["spent_amount"]
            )
            budget_available = available_amount >= command.amount
            evidence_complete = (
                command.category_code not in {"TAX", "CONTRACTOR"}
                or bool(command.supporting_document_version_ids)
            )
            approval_route, required_role, approval_sla_hours = self._payment_approval_route(
                command.amount
            )
            fingerprint = hashlib.sha256(
                json.dumps(
                    command.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            revision_number = context["revision_number"] + 1
            transitions = [
                machine.transition("revision-required", "resubmitted"),
                machine.transition("document-extraction", "extracted"),
                machine.transition(
                    "evidence-check", "complete" if evidence_complete else "incomplete"
                ),
            ]
            current_step = transitions[-1].current_step
            if evidence_complete:
                checked = machine.transition(
                    "budget-check", "available" if budget_available else "unavailable"
                )
                transitions.append(checked)
                current_step = checked.current_step
            approval_id: UUID | None = None
            if evidence_complete and budget_available:
                routed = machine.transition("approval-routing", "routed")
                transitions.append(routed)
                current_step = routed.current_step
                approval_id = uuid4()
                approval_due_at = now + timedelta(hours=approval_sla_hours)
                connection.execute(
                    text("""
                    INSERT INTO governance.approval_requests
                        (approval_request_id, work_item_id, requester_user_id, policy_code,
                         policy_version, status, material_fingerprint, due_at,
                         required_role_code, required_division_code, routing_rule, created_at)
                    VALUES (:approval_id, :work_item_id, :requester, 'FINANCE_PAYMENT',
                            '1.0.0', 'PENDING', :fingerprint, :due_at, :required_role,
                            :required_division, :routing_rule, :now)
                """),
                    {
                        "approval_id": approval_id,
                        "work_item_id": context["work_item_id"],
                        "requester": principal.user_id,
                        "fingerprint": fingerprint,
                        "due_at": approval_due_at,
                        "required_role": required_role,
                        "required_division": (
                            None if required_role == "DIRECTOR" else "FINANCE"
                        ),
                        "routing_rule": approval_route,
                        "now": now,
                    },
                )
                connection.execute(
                    text("""
                    UPDATE finance.budgets
                    SET committed_amount = committed_amount + :amount,
                        updated_at = :now, version = version + 1
                    WHERE budget_id = :budget_id
                """),
                    {"amount": command.amount, "now": now, "budget_id": command.budget_id},
                )
            for version_id in document_ids:
                connection.execute(
                    text("""
                    INSERT INTO platform.evidence
                        (evidence_id, work_item_id, document_version_id, claim_type,
                         status, created_at, created_by)
                    VALUES (:evidence_id, :work_item_id, :version_id,
                            'PAYMENT_REVISION_DOCUMENT', 'SUBMITTED', :now, :actor)
                """),
                    {
                        "evidence_id": uuid4(),
                        "work_item_id": context["work_item_id"],
                        "version_id": version_id,
                        "now": now,
                        "actor": principal.user_id,
                    },
                )
            status = (
                "PENDING_APPROVAL"
                if evidence_complete and budget_available
                else "EXCEPTION"
            )
            connection.execute(
                text("""
                UPDATE finance.payment_requests
                SET budget_id = :budget_id, approval_request_id = :approval_id,
                    document_version_id = :document_version_id, payee_name = :payee_name,
                    vendor_reference = :vendor_reference, category_code = :category_code,
                    purpose = :purpose, amount = :amount, currency = :currency,
                    requested_payment_date = :payment_date, status = :status,
                    budget_available = :budget_available,
                    evidence_complete = :evidence_complete,
                    approval_route = :approval_route,
                    material_fingerprint = :fingerprint,
                    revision_number = :revision_number,
                    updated_at = :now, version = version + 1
                WHERE payment_request_id = :payment_request_id
            """),
                {
                    "budget_id": command.budget_id,
                    "approval_id": approval_id,
                    "document_version_id": command.document_version_id,
                    "payee_name": command.payee_name,
                    "vendor_reference": command.vendor_reference,
                    "category_code": command.category_code,
                    "purpose": command.purpose,
                    "amount": command.amount,
                    "currency": command.currency,
                    "payment_date": command.requested_payment_date,
                    "status": status,
                    "budget_available": budget_available,
                    "evidence_complete": evidence_complete,
                    "approval_route": approval_route,
                    "fingerprint": fingerprint,
                    "revision_number": revision_number,
                    "now": now,
                    "payment_request_id": payment_request_id,
                },
            )
            terminal = current_step == "exception-open"
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs
                SET current_step = :step, status = :status,
                    completed_at = :completed_at, version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": current_step,
                    "status": "COMPLETED" if terminal else "ACTIVE",
                    "completed_at": now if terminal else None,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            connection.execute(
                text("""
                UPDATE platform.work_items
                SET owner_user_id = NULL, status = :status, due_at = :due_at,
                    updated_at = :now, version = version + 1
                WHERE work_item_id = :work_item_id
            """),
                {
                    "status": "PENDING_APPROVAL" if not terminal else "BLOCKED",
                    "due_at": (
                        now + timedelta(hours=approval_sla_hours)
                        if not terminal
                        else now + timedelta(hours=24)
                    ),
                    "now": now,
                    "work_item_id": context["work_item_id"],
                },
            )
            agent_transitions = {"DIA": transitions[1], "CEA": transitions[2]}
            if evidence_complete:
                agent_transitions["BCA"] = transitions[3]
            if evidence_complete and budget_available:
                agent_transitions["ARA"] = transitions[4]
            for plan in plans:
                transition = agent_transitions.get(plan.agent_id)
                agent_run_id = self._record_agent_run(
                    connection,
                    plan,
                    context["workflow_run_id"],
                    context["correlation_id"],
                    {
                        "step": transition.current_step if transition else "NOT_REACHED",
                        "revision_number": revision_number,
                        "budget_available": budget_available,
                        "evidence_complete": evidence_complete,
                        "approval_route": approval_route,
                    },
                    now,
                )
                check_type = {
                    "DIA": "DOCUMENT",
                    "CEA": "EVIDENCE",
                    "BCA": "BUDGET",
                    "ARA": "APPROVAL_ROUTE",
                }.get(plan.agent_id)
                if check_type is not None:
                    passed = {
                        "DOCUMENT": True,
                        "EVIDENCE": evidence_complete,
                        "BUDGET": budget_available,
                        "APPROVAL_ROUTE": evidence_complete and budget_available,
                    }[check_type]
                    connection.execute(
                        text("""
                        INSERT INTO finance.payment_checks
                            (payment_request_id, revision_number, check_type, agent_id,
                             agent_run_id, status, details, checked_at)
                        VALUES (:payment_request_id, :revision_number, :check_type,
                                :agent_id, :agent_run_id, :status,
                                CAST(:details AS jsonb), :now)
                    """),
                        {
                            "payment_request_id": payment_request_id,
                            "revision_number": revision_number,
                            "check_type": check_type,
                            "agent_id": plan.agent_id,
                            "agent_run_id": agent_run_id,
                            "status": "PASSED" if passed else "FAILED",
                            "details": json.dumps({"approval_route": approval_route}),
                            "now": now,
                        },
                    )
            for transition, actor_id in zip(
                transitions,
                (str(principal.user_id), "DIA", "CEA", "BCA", "ARA"),
                strict=False,
            ):
                self._record_transition(
                    connection,
                    context["workflow_run_id"],
                    transition,
                    "HUMAN" if actor_id == str(principal.user_id) else "AGENT",
                    actor_id,
                    now,
                )
            if terminal:
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                    VALUES (:organization_id, :work_item_id, :category,
                            'HIGH', 'OPEN', :owner, :due_at, :now)
                """),
                    {
                        "organization_id": principal.organization_id,
                        "work_item_id": context["work_item_id"],
                        "category": (
                            "EVIDENCE_INCOMPLETE"
                            if not evidence_complete
                            else "BUDGET_INSUFFICIENT"
                        ),
                        "owner": principal.user_id,
                        "due_at": now + timedelta(hours=24),
                        "now": now,
                    },
                )
            connection.execute(
                text("""
                UPDATE platform.reminders SET status = 'CANCELLED'
                WHERE work_item_id = :work_item_id AND status = 'PENDING'
            """),
                {"work_item_id": context["work_item_id"]},
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_revised",
                "payment_request",
                payment_request_id,
                context["correlation_id"],
                {"revision_number": context["revision_number"]},
                {
                    "revision_number": revision_number,
                    "status": status,
                    "approval_route": approval_route,
                },
                command.reason,
            )
            revised_context = dict(context)
            revised_context["approval_request_id"] = approval_id
            result = self._finance_result(
                revised_context,
                current_step,
                status,
                "BLOCKED" if terminal else "PENDING_APPROVAL",
                terminal,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
            return result

    def payment_reconciliation_context(
        self, payment_request_id: UUID, principal: Principal
    ) -> dict[str, object]:
        with self._engine.connect() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            record = (
                connection.execute(
                    text("""
                    SELECT payment_reference, amount, currency
                    FROM finance.payment_records
                    WHERE payment_request_id = :payment_request_id
                """),
                    {"payment_request_id": payment_request_id},
                )
                .mappings()
                .one_or_none()
            )
            if record is None:
                raise ValueError("Catatan pembayaran belum tersedia")
            if context["status"] not in {"PAID", "RECONCILED", "EXCEPTION"}:
                raise ValueError("Payment request belum siap direkonsiliasi")
            return {
                "payment_reference": record["payment_reference"],
                "payment_amount": str(record["amount"]),
                "payment_currency": record["currency"],
            }

    def reconcile_payment(
        self,
        payment_request_id: UUID,
        command: ReconciliationCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plan: AgentExecutionPlan,
        idempotency_key: str,
    ) -> FinanceWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        operation = f"finance.payment_request.reconcile:{payment_request_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_payment(connection, payment_request_id, principal)
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return FinanceWorkflowResult.model_validate(receipt)
            if context["current_step"] != "reconciliation" or context["status"] != "PAID":
                raise ValueError("Payment request belum siap direkonsiliasi")
            record = (
                connection.execute(
                    text("""
                SELECT payment_record_id, payment_reference, amount, currency
                FROM finance.payment_records
                WHERE payment_request_id = :id
            """),
                    {"id": payment_request_id},
                )
                .mappings()
                .one()
            )
            difference = command.transaction_amount - record["amount"]
            matched = (
                difference == 0
                and command.transaction_reference == record["payment_reference"]
                and command.currency == record["currency"]
            )
            transition = machine.transition("reconciliation", "matched" if matched else "mismatch")
            agent_run_id = self._record_agent_run(
                connection,
                plan,
                context["workflow_run_id"],
                context["correlation_id"],
                {"matched": matched, "difference": str(difference)},
                now,
            )
            connection.execute(
                text("""
                INSERT INTO finance.reconciliations
                    (organization_id, payment_request_id, payment_record_id,
                     transaction_reference,
                     transaction_amount, currency, status, difference_amount,
                     created_by_agent_run_id, idempotency_key, created_at)
                VALUES (:organization_id, :payment_request_id, :payment_record_id,
                        :reference, :amount, :currency, :status, :difference, :agent_run_id,
                        :idempotency_key, :now)
            """),
                {
                    "organization_id": principal.organization_id,
                    "payment_request_id": payment_request_id,
                    "payment_record_id": record["payment_record_id"],
                    "reference": command.transaction_reference,
                    "amount": command.transaction_amount,
                    "currency": command.currency,
                    "status": "MATCHED" if matched else "MISMATCH",
                    "difference": difference,
                    "agent_run_id": agent_run_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            status, work_status = (
                ("RECONCILED", "COMPLETED") if matched else ("EXCEPTION", "BLOCKED")
            )
            if matched:
                connection.execute(
                    text("""
                    UPDATE finance.budgets SET committed_amount = committed_amount - :amount,
                        spent_amount = spent_amount + :amount, updated_at = :now,
                        version = version + 1 WHERE budget_id = :budget_id
                """),
                    {"amount": context["amount"], "now": now, "budget_id": context["budget_id"]},
                )
            else:
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                    VALUES (:organization_id, :work_item_id, 'RECONCILIATION_MISMATCH',
                            'HIGH', 'CAPA_REQUIRED', :owner, :due_at, :now)
                """),
                    {
                        "work_item_id": context["work_item_id"],
                        "organization_id": principal.organization_id,
                        "owner": principal.user_id,
                        "due_at": now + timedelta(hours=24),
                        "now": now,
                    },
                )
            self._update_payment_state(
                connection, context, transition.current_step, status, work_status, True, now
            )
            connection.execute(
                text("""
                    UPDATE platform.work_items
                    SET owner_user_id = :owner, due_at = :due_at, updated_at = :now
                    WHERE work_item_id = :work_item_id
                """),
                {
                    "owner": None if matched else principal.user_id,
                    "due_at": None if matched else now + timedelta(hours=24),
                    "now": now,
                    "work_item_id": context["work_item_id"],
                },
            )
            self._record_transition(
                connection, context["workflow_run_id"], transition, "AGENT", "FRA", now
            )
            self._append_audit(
                connection,
                principal,
                "finance.payment_reconciled",
                "payment_request",
                payment_request_id,
                context["correlation_id"],
                None,
                {"matched": matched, "difference": str(difference)},
            )
            result = self._finance_result(
                context,
                transition.current_step,
                status,
                work_status,
                True,
                reconciliation_status="MATCHED" if matched else "MISMATCH",
                difference_amount=difference,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "payment_request",
                payment_request_id,
                result.model_dump(mode="json"),
            )
            return result

    def submit_site_evidence(
        self,
        command: SiteEvidenceCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> PropertyWorkflowResult:
        site_evidence_id, work_item_id, workflow_run_id = uuid4(), uuid4(), uuid4()
        evidence_id, now = uuid4(), datetime.now(UTC)
        variance = command.measured_progress - command.claimed_progress
        machine = StateMachine(definition)
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            actor_exists = connection.execute(
                text("""
                    SELECT 1 FROM identity.users
                    WHERE user_id = :id AND organization_id = :organization_id
                      AND status = 'ACTIVE'
                """),
                {"id": principal.user_id, "organization_id": principal.organization_id},
            ).first()
            if actor_exists is None:
                raise AuthorizationDenied("Pengguna Property belum diprovisikan")
            document = connection.execute(
                text("""
                SELECT 1 FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = :version_id
                  AND d.organization_id = :organization_id
                  AND d.project_id = :project_id
            """),
                {
                    "version_id": command.document_version_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                },
            ).first()
            if document is None:
                raise KeyError("Dokumen bukti lapangan tidak ditemukan pada project")
            division_id = connection.execute(
                text("""
                SELECT division_id FROM identity.divisions
                WHERE organization_id = :organization_id AND code = 'PROPERTY'
            """),
                {"organization_id": principal.organization_id},
            ).scalar_one()
            connection.execute(
                text("""
                INSERT INTO platform.work_items
                    (work_item_id, organization_id, project_id, division_id, title,
                     work_type, priority, status, correlation_id, created_at,
                     created_by, updated_at)
                VALUES (:work_item_id, :organization_id, :project_id, :division_id,
                        :title, 'SITE_EVIDENCE', 'HIGH', 'NEEDS_REVIEW', :correlation_id,
                        :now, :actor, :now)
            """),
                {
                    "work_item_id": work_item_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "division_id": division_id,
                    "title": f"Review progres {command.work_package_code}",
                    "correlation_id": correlation_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text("""
                INSERT INTO workflow.workflow_runs
                    (workflow_run_id, workflow_release_id, work_item_id, current_step,
                     status, correlation_id, idempotency_key, started_at)
                VALUES (:run_id, :release_id, :work_item_id, 'evidence-submitted',
                        'ACTIVE', :correlation_id, :idempotency_key, :now)
            """),
                {
                    "run_id": workflow_run_id,
                    "release_id": release_id,
                    "work_item_id": work_item_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO property.site_evidence
                    (site_evidence_id, organization_id, project_id, work_item_id,
                     workflow_run_id, document_version_id, submitted_by_user_id,
                     work_package_code, claim_date, claimed_progress, measured_progress,
                     variance, measurement_note, status, created_at, updated_at)
                VALUES (:site_evidence_id, :organization_id, :project_id, :work_item_id,
                        :workflow_run_id, :document_version_id, :actor,
                        :work_package_code, :claim_date, :claimed_progress,
                        :measured_progress, :variance, :measurement_note,
                        'PENDING_REVIEW', :now, :now)
            """),
                {
                    "site_evidence_id": site_evidence_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "work_item_id": work_item_id,
                    "workflow_run_id": workflow_run_id,
                    "document_version_id": command.document_version_id,
                    "actor": principal.user_id,
                    "work_package_code": command.work_package_code,
                    "claim_date": command.claim_date,
                    "claimed_progress": command.claimed_progress,
                    "measured_progress": command.measured_progress,
                    "variance": variance,
                    "measurement_note": command.measurement_note,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO platform.evidence
                    (evidence_id, work_item_id, document_version_id, claim_type,
                     status, created_at, created_by)
                VALUES (:evidence_id, :work_item_id, :version_id, 'SITE_PROGRESS',
                        'NEEDS_REVIEW', :now, :actor)
            """),
                {
                    "evidence_id": evidence_id,
                    "work_item_id": work_item_id,
                    "version_id": command.document_version_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            transitions = (
                machine.transition("evidence-submitted", "submitted"),
                machine.transition("evidence-check", "complete"),
                machine.transition("progress-verification", "ready"),
            )
            for plan, transition in zip(plans, transitions[1:], strict=True):
                self._record_agent_run(
                    connection,
                    plan,
                    workflow_run_id,
                    correlation_id,
                    {
                        "step": transition.current_step,
                        "claimed_progress": str(command.claimed_progress),
                        "measured_progress": str(command.measured_progress),
                        "variance": str(variance),
                    },
                    now,
                )
            self._record_transition(
                connection, workflow_run_id, transitions[0], "HUMAN", principal.user_id, now
            )
            for transition, agent_id in zip(transitions[1:], ("CEA", "TPA"), strict=True):
                self._record_transition(
                    connection, workflow_run_id, transition, "AGENT", agent_id, now
                )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = 'human-review',
                    version = version + 1 WHERE workflow_run_id = :run_id
            """),
                {"run_id": workflow_run_id},
            )
            self._append_audit(
                connection,
                principal,
                "property.site_evidence_submitted",
                "site_evidence",
                site_evidence_id,
                correlation_id,
                None,
                {
                    "work_package_code": command.work_package_code,
                    "claimed_progress": str(command.claimed_progress),
                    "measured_progress": str(command.measured_progress),
                    "variance": str(variance),
                },
            )
        return PropertyWorkflowResult(
            site_evidence_id=site_evidence_id,
            workflow_run_id=workflow_run_id,
            work_item_id=work_item_id,
            current_step="human-review",
            workflow_status="ACTIVE",
            evidence_status="PENDING_REVIEW",
            work_item_status=WorkItemStatus.NEEDS_REVIEW,
            claimed_progress=command.claimed_progress,
            measured_progress=command.measured_progress,
            variance=variance,
            terminal=False,
            correlation_id=correlation_id,
        )

    def site_evidence_review_context(
        self, site_evidence_id: UUID, principal: Principal
    ) -> dict[str, object]:
        """Authorize the reviewer before any runtime work is dispatched."""

        with self._engine.connect() as connection:
            context = self._load_site_evidence(connection, site_evidence_id, principal)
        if context["current_step"] != "human-review" or context["status"] != "PENDING_REVIEW":
            raise ValueError("Bukti lapangan tidak menunggu review Property")
        if context["submitted_by_user_id"] == principal.user_id:
            raise AuthorizationDenied("Pengunggah tidak dapat mereview buktinya sendiri")
        return {
            "claimed_progress": str(context["claimed_progress"]),
            "measured_progress": str(context["measured_progress"]),
            "variance": str(context["variance"]),
        }

    def review_site_evidence(
        self,
        site_evidence_id: UUID,
        command: PropertyReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plan: AgentExecutionPlan,
    ) -> PropertyWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        with self._engine.begin() as connection:
            context = self._load_site_evidence(connection, site_evidence_id, principal)
            if context["current_step"] != "human-review" or context["status"] != "PENDING_REVIEW":
                raise ValueError("Bukti lapangan tidak menunggu review Property")
            if context["submitted_by_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pengunggah tidak dapat mereview buktinya sendiri")
            outcome = "accepted" if command.decision == "ACCEPTED" else "variance"
            transition = machine.transition("human-review", outcome)
            agent_run_id = self._record_agent_run(
                connection,
                plan,
                context["workflow_run_id"],
                context["correlation_id"],
                {
                    "decision": command.decision,
                    "verified_progress": str(command.verified_progress),
                },
                now,
            )
            kpi_snapshot_id: UUID | None = None
            exception_id: UUID | None = None
            capa_id: UUID | None = None
            evidence_status = "ACCEPTED" if command.decision == "ACCEPTED" else "VARIANCE"
            work_status = "COMPLETED" if command.decision == "ACCEPTED" else "BLOCKED"
            if command.decision == "ACCEPTED":
                kpi_snapshot_id = uuid4()
                connection.execute(
                    text("""
                    INSERT INTO executive.kpi_snapshots
                        (kpi_snapshot_id, organization_id, project_id, metric_code,
                         period_start, period_end, value, unit, source_entity_type,
                         source_entity_id, source_agent_run_id, verification_status,
                         created_at)
                    VALUES (:snapshot_id, :organization_id, :project_id,
                            'PROPERTY_VERIFIED_PROGRESS', :period, :period, :value,
                            'PERCENT', 'site_evidence', :site_evidence_id, :agent_run_id,
                            'VERIFIED', :now)
                """),
                    {
                        "snapshot_id": kpi_snapshot_id,
                        "organization_id": principal.organization_id,
                        "project_id": context["project_id"],
                        "period": context["claim_date"],
                        "value": command.verified_progress,
                        "site_evidence_id": site_evidence_id,
                        "agent_run_id": agent_run_id,
                        "now": now,
                    },
                )
            else:
                exception_id, capa_id = uuid4(), uuid4()
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (exception_id, organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                    VALUES (:exception_id, :organization_id, :work_item_id,
                            'SITE_PROGRESS_VARIANCE',
                            'HIGH', 'CAPA_REQUIRED', :owner, :due_at, :now)
                """),
                    {
                        "exception_id": exception_id,
                        "organization_id": principal.organization_id,
                        "work_item_id": context["work_item_id"],
                        "owner": context["submitted_by_user_id"],
                        "due_at": now + timedelta(days=7),
                        "now": now,
                    },
                )
                connection.execute(
                    text("""
                    INSERT INTO governance.capas
                        (capa_id, exception_id, status, root_cause, corrective_action,
                         preventive_action, due_at, created_at)
                    VALUES (:capa_id, :exception_id, 'OPEN',
                            'Menunggu analisis pemilik proses Property',
                            'Verifikasi ulang pengukuran dan bukti progres',
                            'Review metode pengukuran sebelum klaim berikutnya',
                            :due_at, :now)
                """),
                    {
                        "capa_id": capa_id,
                        "exception_id": exception_id,
                        "due_at": now + timedelta(days=7),
                        "now": now,
                    },
                )
            connection.execute(
                text("""
                UPDATE property.site_evidence
                SET status = :status, reviewer_user_id = :reviewer,
                    verified_progress = :verified_progress, review_notes = :notes,
                    reviewed_at = :now, updated_at = :now, version = version + 1
                WHERE site_evidence_id = :site_evidence_id
            """),
                {
                    "status": evidence_status,
                    "reviewer": principal.user_id,
                    "verified_progress": command.verified_progress,
                    "notes": command.notes,
                    "now": now,
                    "site_evidence_id": site_evidence_id,
                },
            )
            connection.execute(
                text("""
                UPDATE platform.evidence SET status = :status
                WHERE work_item_id = :work_item_id AND claim_type = 'SITE_PROGRESS'
            """),
                {
                    "status": "ACCEPTED" if command.decision == "ACCEPTED" else "REJECTED",
                    "work_item_id": context["work_item_id"],
                },
            )
            connection.execute(
                text("""
                UPDATE platform.work_items SET status = :status, updated_at = :now,
                    version = version + 1 WHERE work_item_id = :work_item_id
            """),
                {"status": work_status, "now": now, "work_item_id": context["work_item_id"]},
            )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = :step,
                    status = 'COMPLETED', completed_at = :now, version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": transition.current_step,
                    "now": now,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            self._record_transition(
                connection,
                context["workflow_run_id"],
                transition,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._append_audit(
                connection,
                principal,
                "property.site_evidence_reviewed",
                "site_evidence",
                site_evidence_id,
                context["correlation_id"],
                {"status": context["status"]},
                {
                    "status": evidence_status,
                    "verified_progress": str(command.verified_progress),
                    "kpi_snapshot_id": str(kpi_snapshot_id) if kpi_snapshot_id else None,
                    "exception_id": str(exception_id) if exception_id else None,
                    "capa_id": str(capa_id) if capa_id else None,
                },
            )
            return PropertyWorkflowResult(
                site_evidence_id=site_evidence_id,
                workflow_run_id=context["workflow_run_id"],
                work_item_id=context["work_item_id"],
                current_step=transition.current_step,
                workflow_status="COMPLETED",
                evidence_status=evidence_status,
                work_item_status=WorkItemStatus(work_status),
                claimed_progress=context["claimed_progress"],
                measured_progress=context["measured_progress"],
                variance=context["variance"],
                kpi_snapshot_id=kpi_snapshot_id,
                exception_id=exception_id,
                capa_id=capa_id,
                terminal=True,
                correlation_id=context["correlation_id"],
            )

    @staticmethod
    def _load_site_evidence(
        connection: Any, site_evidence_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
                SELECT se.site_evidence_id, se.project_id, se.work_item_id,
                       se.workflow_run_id, se.submitted_by_user_id, se.claim_date,
                       se.claimed_progress, se.measured_progress, se.variance, se.status,
                       wr.current_step, wr.correlation_id
                FROM property.site_evidence se
                JOIN workflow.workflow_runs wr ON wr.workflow_run_id = se.workflow_run_id
                WHERE se.site_evidence_id = :site_evidence_id
                  AND se.organization_id = :organization_id
                FOR UPDATE OF se, wr
            """),
                {
                    "site_evidence_id": site_evidence_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Bukti lapangan tidak ditemukan")
        if not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke project Property")
        return cast(Mapping[str, Any], row)

    def submit_legal_document(
        self,
        command: LegalSubmissionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> LegalWorkflowResult:
        legal_case_id, work_item_id, workflow_run_id = uuid4(), uuid4(), uuid4()
        evidence_id, now = uuid4(), datetime.now(UTC)
        machine = StateMachine(definition)
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            actor_exists = connection.execute(
                text("""
                    SELECT 1 FROM identity.users
                    WHERE user_id = :id AND organization_id = :organization_id
                      AND status = 'ACTIVE'
                """),
                {"id": principal.user_id, "organization_id": principal.organization_id},
            ).first()
            if actor_exists is None:
                raise AuthorizationDenied("Pengguna Legal belum diprovisikan")
            document_exists = connection.execute(
                text("""
                SELECT 1 FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = :version_id
                  AND d.organization_id = :organization_id
                  AND d.project_id = :project_id
            """),
                {
                    "version_id": command.document_version_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                },
            ).first()
            if document_exists is None:
                raise KeyError("Dokumen Legal tidak ditemukan pada project")
            division_id = connection.execute(
                text("""
                SELECT division_id FROM identity.divisions
                WHERE organization_id = :organization_id AND code = 'LEGAL'
            """),
                {"organization_id": principal.organization_id},
            ).scalar_one()
            connection.execute(
                text("""
                INSERT INTO platform.work_items
                    (work_item_id, organization_id, project_id, division_id, title,
                     work_type, priority, status, correlation_id, created_at,
                     created_by, updated_at)
                VALUES (:work_item_id, :organization_id, :project_id, :division_id,
                        :title, 'LEGAL_REVIEW', 'HIGH', 'NEEDS_REVIEW', :correlation_id,
                        :now, :actor, :now)
            """),
                {
                    "work_item_id": work_item_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "division_id": division_id,
                    "title": f"Review {command.document_type.lower()}: {command.title}",
                    "correlation_id": correlation_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text("""
                INSERT INTO workflow.workflow_runs
                    (workflow_run_id, workflow_release_id, work_item_id, current_step,
                     status, correlation_id, idempotency_key, started_at)
                VALUES (:run_id, :release_id, :work_item_id, 'document-submitted',
                        'ACTIVE', :correlation_id, :idempotency_key, :now)
            """),
                {
                    "run_id": workflow_run_id,
                    "release_id": release_id,
                    "work_item_id": work_item_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO legal.cases
                    (legal_case_id, organization_id, project_id, work_item_id,
                     workflow_run_id, document_version_id, submitted_by_user_id,
                     document_type, reference_code, title, counterparty,
                     source_authority, effective_date, expiry_date, status,
                     created_at, updated_at)
                VALUES (:legal_case_id, :organization_id, :project_id, :work_item_id,
                        :workflow_run_id, :document_version_id, :actor,
                        :document_type, :reference_code, :title, :counterparty,
                        :source_authority, :effective_date, :expiry_date,
                        'PENDING_REVIEW', :now, :now)
            """),
                {
                    "legal_case_id": legal_case_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "work_item_id": work_item_id,
                    "workflow_run_id": workflow_run_id,
                    "document_version_id": command.document_version_id,
                    "actor": principal.user_id,
                    "document_type": command.document_type,
                    "reference_code": command.reference_code,
                    "title": command.title,
                    "counterparty": command.counterparty,
                    "source_authority": command.source_authority,
                    "effective_date": command.effective_date,
                    "expiry_date": command.expiry_date,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO platform.evidence
                    (evidence_id, work_item_id, document_version_id, claim_type,
                     status, created_at, created_by)
                VALUES (:evidence_id, :work_item_id, :version_id, 'LEGAL_SOURCE',
                        'NEEDS_REVIEW', :now, :actor)
            """),
                {
                    "evidence_id": evidence_id,
                    "work_item_id": work_item_id,
                    "version_id": command.document_version_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            transitions = (
                machine.transition("document-submitted", "submitted"),
                machine.transition("document-extraction", "extracted"),
                machine.transition("legal-analysis", "analyzed"),
                machine.transition("evidence-check", "complete"),
            )
            for plan, transition in zip(plans, transitions[1:], strict=True):
                self._record_agent_run(
                    connection,
                    plan,
                    workflow_run_id,
                    correlation_id,
                    {
                        "step": transition.current_step,
                        "document_type": command.document_type,
                        "reference_code": command.reference_code,
                        "human_review_required": True,
                    },
                    now,
                )
            self._record_transition(
                connection, workflow_run_id, transitions[0], "HUMAN", principal.user_id, now
            )
            for plan, transition in zip(plans, transitions[1:], strict=True):
                self._record_transition(
                    connection, workflow_run_id, transition, "AGENT", plan.agent_id, now
                )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = 'legal-review',
                    version = version + 1 WHERE workflow_run_id = :run_id
            """),
                {"run_id": workflow_run_id},
            )
            self._append_audit(
                connection,
                principal,
                "legal.document_submitted",
                "legal_case",
                legal_case_id,
                correlation_id,
                None,
                {
                    "document_type": command.document_type,
                    "reference_code": command.reference_code,
                    "current_step": "legal-review",
                },
            )
        return LegalWorkflowResult(
            legal_case_id=legal_case_id,
            workflow_run_id=workflow_run_id,
            work_item_id=work_item_id,
            document_type=command.document_type,
            current_step="legal-review",
            workflow_status="ACTIVE",
            case_status="PENDING_REVIEW",
            work_item_status=WorkItemStatus.NEEDS_REVIEW,
            terminal=False,
            correlation_id=correlation_id,
        )

    def review_legal_document(
        self,
        legal_case_id: UUID,
        command: LegalReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> LegalWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        with self._engine.begin() as connection:
            context = self._load_legal_case(connection, legal_case_id, principal)
            if context["current_step"] != "legal-review" or context["status"] != "PENDING_REVIEW":
                raise ValueError("Dokumen tidak menunggu review Legal")
            if context["submitted_by_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pengaju tidak dapat mereview dokumen Legal sendiri")
            if command.decision == "APPROVED" and command.legal_status == "NOT_APPROVED":
                raise ValueError("Keputusan APPROVED tidak sesuai dengan status NOT_APPROVED")
            if command.decision == "REJECTED" and command.legal_status != "NOT_APPROVED":
                raise ValueError("Keputusan REJECTED wajib menggunakan status NOT_APPROVED")
            if (
                context["document_type"] == "PERMIT"
                and command.decision == "APPROVED"
                and not command.official_source_verified
            ):
                raise ValueError("Izin tidak dapat disetujui sebelum sumber resmi diverifikasi")
            outcome = {
                "APPROVED": "approved",
                "REVISION_REQUESTED": "revision_requested",
                "REJECTED": "rejected",
            }[command.decision]
            transition = machine.transition("legal-review", outcome)
            exception_id: UUID | None = None
            work_status = "COMPLETED" if command.decision == "APPROVED" else "BLOCKED"
            if command.decision != "APPROVED":
                exception_id = uuid4()
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (exception_id, organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                    VALUES (:exception_id, :organization_id, :work_item_id,
                            :category, :severity,
                            'OPEN', :owner, :due_at, :now)
                """),
                    {
                        "exception_id": exception_id,
                        "organization_id": principal.organization_id,
                        "work_item_id": context["work_item_id"],
                        "category": f"{context['document_type']}_REVIEW_NOT_APPROVED",
                        "severity": "HIGH" if context["document_type"] == "PERMIT" else "MEDIUM",
                        "owner": context["submitted_by_user_id"],
                        "due_at": now + timedelta(days=7),
                        "now": now,
                    },
                )
            connection.execute(
                text("""
                UPDATE legal.cases
                SET status = :status, reviewer_user_id = :reviewer,
                    legal_status = :legal_status,
                    official_source_verified = :official_source_verified,
                    review_notes = :notes, reviewed_at = :now, updated_at = :now,
                    version = version + 1
                WHERE legal_case_id = :legal_case_id
            """),
                {
                    "status": command.decision,
                    "reviewer": principal.user_id,
                    "legal_status": command.legal_status,
                    "official_source_verified": command.official_source_verified,
                    "notes": command.notes,
                    "now": now,
                    "legal_case_id": legal_case_id,
                },
            )
            evidence_status = (
                "ACCEPTED"
                if command.decision == "APPROVED"
                else "REJECTED"
                if command.decision == "REJECTED"
                else "NEEDS_REVIEW"
            )
            connection.execute(
                text("""
                UPDATE platform.evidence SET status = :status
                WHERE work_item_id = :work_item_id AND claim_type = 'LEGAL_SOURCE'
            """),
                {"status": evidence_status, "work_item_id": context["work_item_id"]},
            )
            connection.execute(
                text("""
                UPDATE platform.work_items SET status = :status, updated_at = :now,
                    version = version + 1 WHERE work_item_id = :work_item_id
            """),
                {"status": work_status, "now": now, "work_item_id": context["work_item_id"]},
            )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = :step,
                    status = 'COMPLETED', completed_at = :now, version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": transition.current_step,
                    "now": now,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            self._record_transition(
                connection,
                context["workflow_run_id"],
                transition,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._append_audit(
                connection,
                principal,
                "legal.document_reviewed",
                "legal_case",
                legal_case_id,
                context["correlation_id"],
                {"status": context["status"]},
                {
                    "status": command.decision,
                    "legal_status": command.legal_status,
                    "official_source_verified": command.official_source_verified,
                    "exception_id": str(exception_id) if exception_id else None,
                },
            )
            return LegalWorkflowResult(
                legal_case_id=legal_case_id,
                workflow_run_id=context["workflow_run_id"],
                work_item_id=context["work_item_id"],
                document_type=context["document_type"],
                current_step=transition.current_step,
                workflow_status="COMPLETED",
                case_status=command.decision,
                work_item_status=WorkItemStatus(work_status),
                exception_id=exception_id,
                terminal=True,
                correlation_id=context["correlation_id"],
            )

    @staticmethod
    def _load_legal_case(
        connection: Any, legal_case_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
                SELECT lc.legal_case_id, lc.project_id, lc.work_item_id,
                       lc.workflow_run_id, lc.submitted_by_user_id, lc.document_type,
                       lc.status, wr.current_step, wr.correlation_id
                FROM legal.cases lc
                JOIN workflow.workflow_runs wr ON wr.workflow_run_id = lc.workflow_run_id
                WHERE lc.legal_case_id = :legal_case_id
                  AND lc.organization_id = :organization_id
                FOR UPDATE OF lc, wr
            """),
                {
                    "legal_case_id": legal_case_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Kasus Legal tidak ditemukan")
        if not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke project Legal")
        return cast(Mapping[str, Any], row)

    def submit_recruitment_request(
        self,
        command: RecruitmentRequestCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> RecruitmentWorkflowResult:
        request_id, candidate_id, work_item_id, workflow_run_id = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        evidence_id, now = uuid4(), datetime.now(UTC)
        missing_criteria = sorted(set(command.required_criteria) - set(command.met_criteria))
        screening_status = "COMPLETE" if not missing_criteria else "INCOMPLETE"
        machine = StateMachine(definition)
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            actor_exists = connection.execute(
                text("""
                    SELECT 1 FROM identity.users
                    WHERE user_id = :id AND organization_id = :organization_id
                      AND status = 'ACTIVE'
                """),
                {"id": principal.user_id, "organization_id": principal.organization_id},
            ).first()
            if actor_exists is None:
                raise AuthorizationDenied("Pengaju rekrutmen belum diprovisikan")
            document_exists = connection.execute(
                text("""
                SELECT 1 FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = :version_id
                  AND d.organization_id = :organization_id
                  AND d.project_id = :project_id
            """),
                {
                    "version_id": command.candidate_document_version_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                },
            ).first()
            if document_exists is None:
                raise KeyError("Dokumen kandidat sanitasi tidak ditemukan pada project")
            division_id = connection.execute(
                text("""
                SELECT division_id FROM identity.divisions
                WHERE organization_id = :organization_id AND code = 'HR'
            """),
                {"organization_id": principal.organization_id},
            ).scalar_one()
            connection.execute(
                text("""
                INSERT INTO platform.work_items
                    (work_item_id, organization_id, project_id, division_id, title,
                     work_type, priority, status, correlation_id, created_at,
                     created_by, updated_at)
                VALUES (:work_item_id, :organization_id, :project_id, :division_id,
                        :title, 'RECRUITMENT', 'HIGH', 'NEEDS_REVIEW', :correlation_id,
                        :now, :actor, :now)
            """),
                {
                    "work_item_id": work_item_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "division_id": division_id,
                    "title": f"Rekrutmen: {command.position_title}",
                    "correlation_id": correlation_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text("""
                INSERT INTO workflow.workflow_runs
                    (workflow_run_id, workflow_release_id, work_item_id, current_step,
                     status, correlation_id, idempotency_key, started_at)
                VALUES (:run_id, :release_id, :work_item_id, 'request-submitted',
                        'ACTIVE', :correlation_id, :idempotency_key, :now)
            """),
                {
                    "run_id": workflow_run_id,
                    "release_id": release_id,
                    "work_item_id": work_item_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO hr.recruitment_requests
                    (recruitment_request_id, organization_id, project_id, work_item_id,
                     workflow_run_id, submitted_by_user_id, position_title,
                     requesting_division_code, employment_type, headcount,
                     justification, criteria_version, status, created_at, updated_at)
                VALUES (:request_id, :organization_id, :project_id, :work_item_id,
                        :workflow_run_id, :actor, :position_title,
                        :requesting_division_code, :employment_type, :headcount,
                        :justification, :criteria_version, 'PENDING_HR_REVIEW', :now, :now)
            """),
                {
                    "request_id": request_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "work_item_id": work_item_id,
                    "workflow_run_id": workflow_run_id,
                    "actor": principal.user_id,
                    "position_title": command.position_title,
                    "requesting_division_code": command.requesting_division_code,
                    "employment_type": command.employment_type,
                    "headcount": command.headcount,
                    "justification": command.justification,
                    "criteria_version": command.criteria_version,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO hr.candidates
                    (candidate_id, recruitment_request_id, document_version_id,
                     candidate_alias, required_criteria, met_criteria, missing_criteria,
                     screening_status, created_at)
                VALUES (:candidate_id, :request_id, :document_version_id,
                        :candidate_alias, CAST(:required AS jsonb), CAST(:met AS jsonb),
                        CAST(:missing AS jsonb), :screening_status, :now)
            """),
                {
                    "candidate_id": candidate_id,
                    "request_id": request_id,
                    "document_version_id": command.candidate_document_version_id,
                    "candidate_alias": command.candidate_alias,
                    "required": json.dumps(command.required_criteria),
                    "met": json.dumps(command.met_criteria),
                    "missing": json.dumps(missing_criteria),
                    "screening_status": screening_status,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO platform.evidence
                    (evidence_id, work_item_id, document_version_id, claim_type,
                     status, created_at, created_by)
                VALUES (:evidence_id, :work_item_id, :version_id,
                        'CANDIDATE_SANITIZED', 'NEEDS_REVIEW', :now, :actor)
            """),
                {
                    "evidence_id": evidence_id,
                    "work_item_id": work_item_id,
                    "version_id": command.candidate_document_version_id,
                    "now": now,
                    "actor": principal.user_id,
                },
            )
            transitions = [
                machine.transition("request-submitted", "valid"),
                machine.transition("sop-plan", "ready"),
                machine.transition("candidate-screening", "ready_for_review"),
            ]
            for plan, transition in zip(plans, transitions[1:], strict=True):
                output = {
                    "step": transition.current_step,
                    "criteria_version": command.criteria_version,
                    "screening_status": screening_status,
                    "missing_criteria": missing_criteria,
                    "human_decision_required": True,
                }
                self._record_agent_run(
                    connection, plan, workflow_run_id, correlation_id, output, now
                )
            self._record_transition(
                connection, workflow_run_id, transitions[0], "HUMAN", principal.user_id, now
            )
            for plan, transition in zip(plans, transitions[1:], strict=True):
                self._record_transition(
                    connection, workflow_run_id, transition, "AGENT", plan.agent_id, now
                )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = 'hr-review',
                    version = version + 1 WHERE workflow_run_id = :run_id
            """),
                {"run_id": workflow_run_id},
            )
            self._append_audit(
                connection,
                principal,
                "hr.recruitment_submitted",
                "recruitment_request",
                request_id,
                correlation_id,
                None,
                {
                    "position_title": command.position_title,
                    "criteria_version": command.criteria_version,
                    "screening_status": screening_status,
                    "missing_criteria": missing_criteria,
                },
            )
        return RecruitmentWorkflowResult(
            recruitment_request_id=request_id,
            candidate_id=candidate_id,
            workflow_run_id=workflow_run_id,
            work_item_id=work_item_id,
            current_step="hr-review",
            workflow_status="ACTIVE",
            recruitment_status="PENDING_HR_REVIEW",
            screening_status=screening_status,
            missing_criteria=missing_criteria,
            work_item_status=WorkItemStatus.NEEDS_REVIEW,
            terminal=False,
            correlation_id=correlation_id,
        )

    def decide_recruitment(
        self,
        recruitment_request_id: UUID,
        command: RecruitmentDecisionCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan | None,
    ) -> RecruitmentWorkflowResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        with self._engine.begin() as connection:
            context = self._load_recruitment(connection, recruitment_request_id, principal)
            if context["current_step"] != "hr-review" or context["status"] != "PENDING_HR_REVIEW":
                raise ValueError("Permintaan rekrutmen tidak menunggu keputusan HR")
            if context["submitted_by_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pengaju tidak dapat memutus rekrutmennya sendiri")
            outcome = "selected" if command.decision == "SELECTED" else "rejected"
            transition = machine.transition("hr-review", outcome)
            checklist_id: UUID | None = None
            if command.decision == "SELECTED":
                if agent_plan is None:
                    raise ValueError("HPA execution plan diperlukan untuk kandidat terpilih")
                checklist_id = uuid4()
                agent_run_id = self._record_agent_run(
                    connection,
                    agent_plan,
                    context["workflow_run_id"],
                    context["correlation_id"],
                    {
                        "checklist_id": str(checklist_id),
                        "requirements": command.personnel_requirements,
                        "status": "OPEN",
                    },
                    now,
                )
                connection.execute(
                    text("""
                    INSERT INTO hr.personnel_checklists
                        (personnel_checklist_id, recruitment_request_id, candidate_id,
                         created_by_agent_run_id, status, created_at)
                    VALUES (:checklist_id, :request_id, :candidate_id,
                            :agent_run_id, 'OPEN', :now)
                """),
                    {
                        "checklist_id": checklist_id,
                        "request_id": recruitment_request_id,
                        "candidate_id": context["candidate_id"],
                        "agent_run_id": agent_run_id,
                        "now": now,
                    },
                )
                for requirement in command.personnel_requirements:
                    connection.execute(
                        text("""
                        INSERT INTO hr.personnel_requirements
                            (personnel_checklist_id, requirement_code, status, created_at)
                        VALUES (:checklist_id, :requirement, 'MISSING', :now)
                    """),
                        {
                            "checklist_id": checklist_id,
                            "requirement": requirement,
                            "now": now,
                        },
                    )
            connection.execute(
                text("""
                UPDATE hr.recruitment_requests
                SET status = :status, reviewer_user_id = :reviewer,
                    decision_notes = :notes, decided_at = :now, updated_at = :now,
                    version = version + 1
                WHERE recruitment_request_id = :request_id
            """),
                {
                    "status": command.decision,
                    "reviewer": principal.user_id,
                    "notes": command.notes,
                    "now": now,
                    "request_id": recruitment_request_id,
                },
            )
            connection.execute(
                text("""
                UPDATE platform.evidence SET status = :status
                WHERE work_item_id = :work_item_id
                  AND claim_type = 'CANDIDATE_SANITIZED'
            """),
                {
                    "status": "ACCEPTED" if command.decision == "SELECTED" else "REJECTED",
                    "work_item_id": context["work_item_id"],
                },
            )
            connection.execute(
                text("""
                UPDATE platform.work_items SET status = 'COMPLETED', updated_at = :now,
                    version = version + 1 WHERE work_item_id = :work_item_id
            """),
                {"now": now, "work_item_id": context["work_item_id"]},
            )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = :step,
                    status = 'COMPLETED', completed_at = :now, version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": transition.current_step,
                    "now": now,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            self._record_transition(
                connection,
                context["workflow_run_id"],
                transition,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._append_audit(
                connection,
                principal,
                "hr.recruitment_decided",
                "recruitment_request",
                recruitment_request_id,
                context["correlation_id"],
                {"status": context["status"]},
                {
                    "status": command.decision,
                    "personnel_checklist_id": str(checklist_id) if checklist_id else None,
                },
            )
            return RecruitmentWorkflowResult(
                recruitment_request_id=recruitment_request_id,
                candidate_id=context["candidate_id"],
                workflow_run_id=context["workflow_run_id"],
                work_item_id=context["work_item_id"],
                current_step=transition.current_step,
                workflow_status="COMPLETED",
                recruitment_status=command.decision,
                screening_status=context["screening_status"],
                missing_criteria=context["missing_criteria"],
                work_item_status=WorkItemStatus.COMPLETED,
                personnel_checklist_id=checklist_id,
                terminal=True,
                correlation_id=context["correlation_id"],
            )

    def recruitment_decision_context(
        self, recruitment_request_id: UUID, principal: Principal
    ) -> dict[str, object]:
        """Authorize an HR decision before preparing an optional HPA run."""

        with self._engine.connect() as connection:
            context = self._load_recruitment(
                connection, recruitment_request_id, principal
            )
        if context["current_step"] != "hr-review" or context["status"] != "PENDING_HR_REVIEW":
            raise ValueError("Permintaan rekrutmen tidak menunggu keputusan HR")
        if context["submitted_by_user_id"] == principal.user_id:
            raise AuthorizationDenied("Pengaju tidak dapat memutus rekrutmennya sendiri")
        return {
            "screening_status": str(context["screening_status"]),
            "missing_criteria": list(context["missing_criteria"]),
        }

    @staticmethod
    def _load_recruitment(
        connection: Any, recruitment_request_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
                SELECT rr.recruitment_request_id, rr.project_id, rr.work_item_id,
                       rr.workflow_run_id, rr.submitted_by_user_id, rr.status,
                       c.candidate_id, c.screening_status, c.missing_criteria,
                       wr.current_step, wr.correlation_id
                FROM hr.recruitment_requests rr
                JOIN hr.candidates c
                  ON c.recruitment_request_id = rr.recruitment_request_id
                JOIN workflow.workflow_runs wr ON wr.workflow_run_id = rr.workflow_run_id
                WHERE rr.recruitment_request_id = :request_id
                  AND rr.organization_id = :organization_id
                FOR UPDATE OF rr, wr
            """),
                {
                    "request_id": recruitment_request_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Permintaan rekrutmen tidak ditemukan")
        if not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke project rekrutmen")
        return cast(Mapping[str, Any], row)

    def prepare_executive_brief(
        self, command: ExecutiveBriefCreate, principal: Principal
    ) -> dict[str, object]:
        """Build agent inputs from persisted facts before creating the snapshot."""

        parameters = {
            "organization_id": principal.organization_id,
            "project_id": command.project_id,
            "period_start": command.period_start,
            "period_end": command.period_end,
        }
        with self._engine.connect() as connection:
            if command.project_id is not None:
                self._assert_project(connection, command.project_id, principal)
            facts = self._executive_counts(connection, principal, command)
            capa_due_dates = list(
                connection.execute(
                    text(
                        """
                        SELECT c.due_at
                        FROM governance.capas c
                        JOIN governance.exceptions e ON e.exception_id = c.exception_id
                        LEFT JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
                        WHERE e.organization_id = :organization_id
                          AND c.status <> 'CLOSED'
                          AND c.due_at IS NOT NULL
                          AND (CAST(:project_id AS uuid) IS NULL
                               OR wi.project_id = CAST(:project_id AS uuid))
                          AND c.created_at >= CAST(:period_start AS date)
                          AND c.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                        ORDER BY c.due_at
                        """
                    ),
                    parameters,
                ).scalars()
            )
            approval_due_dates = list(
                connection.execute(
                    text(
                        """
                        SELECT r.scheduled_for
                        FROM platform.reminders r
                        JOIN governance.approval_requests ar
                          ON ar.approval_request_id = r.approval_request_id
                        JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
                        WHERE wi.organization_id = :organization_id
                          AND ar.status = 'PENDING'
                          AND r.status = 'PENDING'
                          AND (CAST(:project_id AS uuid) IS NULL
                               OR wi.project_id = CAST(:project_id AS uuid))
                          AND ar.created_at >= CAST(:period_start AS date)
                          AND ar.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                        ORDER BY r.scheduled_for
                        """
                    ),
                    parameters,
                ).scalars()
            )
        period = f"{command.period_start}:{command.period_end}"
        return {
            "facts": facts,
            "source_references": [
                f"system-fact:{period}:{name}" for name in sorted(facts)
            ],
            "capa_due_dates": [
                value.isoformat() for value in capa_due_dates if value is not None
            ],
            "approval_due_dates": [
                value.isoformat() for value in approval_due_dates if value is not None
            ],
        }

    def generate_executive_brief(
        self,
        command: ExecutiveBriefCreate,
        principal: Principal,
        definition: WorkflowDefinition,
        plans: tuple[AgentExecutionPlan, ...],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutiveBriefResult:
        snapshot_id, brief_id, workflow_run_id = uuid4(), uuid4(), uuid4()
        now, machine = datetime.now(UTC), StateMachine(definition)
        with self._engine.begin() as connection:
            if command.project_id is not None:
                self._assert_project(connection, command.project_id, principal)
            facts = self._executive_counts(connection, principal, command)
            source_references = [
                f"executive_snapshot:{snapshot_id}#facts.{name}" for name in sorted(facts)
            ]
            source_hash = hashlib.sha256(
                json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            narrative = self._executive_narrative(command, facts)
            connection.execute(
                text("""
                INSERT INTO executive.snapshots
                    (executive_snapshot_id, organization_id, project_id, period_start,
                     period_end, facts, source_hash, created_at)
                VALUES (:snapshot_id, :organization_id, :project_id, :period_start,
                        :period_end, CAST(:facts AS jsonb), :source_hash, :now)
            """),
                {
                    "snapshot_id": snapshot_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "period_start": command.period_start,
                    "period_end": command.period_end,
                    "facts": json.dumps(facts, sort_keys=True),
                    "source_hash": source_hash,
                    "now": now,
                },
            )
            release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text("""
                INSERT INTO workflow.workflow_runs
                    (workflow_run_id, workflow_release_id, work_item_id, current_step,
                     status, correlation_id, idempotency_key, started_at)
                VALUES (:run_id, :release_id, NULL, 'snapshot-created', 'ACTIVE',
                        :correlation_id, :idempotency_key, :now)
            """),
                {
                    "run_id": workflow_run_id,
                    "release_id": release_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            transitions = (
                machine.transition("snapshot-created", "ready"),
                machine.transition("kpi-aggregation", "complete"),
                machine.transition("risk-aggregation", "complete"),
                machine.transition("approval-aggregation", "complete"),
                machine.transition("brief-generation", "sourced"),
            )
            agent_run_ids: dict[str, UUID] = {}
            for plan, transition in zip(plans, transitions[1:], strict=True):
                agent_run_ids[plan.agent_id] = self._record_agent_run(
                    connection,
                    plan,
                    workflow_run_id,
                    correlation_id,
                    {
                        "step": transition.current_step,
                        "snapshot_id": str(snapshot_id),
                        "facts": facts,
                        "source_references": source_references,
                    },
                    now,
                )
            self._record_transition(
                connection,
                workflow_run_id,
                transitions[0],
                "SYSTEM",
                "executive-read-model",
                now,
            )
            for plan, transition in zip(plans, transitions[1:], strict=True):
                self._record_transition(
                    connection, workflow_run_id, transition, "AGENT", plan.agent_id, now
                )
            connection.execute(
                text("""
                INSERT INTO executive.briefs
                    (executive_brief_id, executive_snapshot_id, workflow_run_id, title,
                     narrative, source_references, status, generated_by_agent_run_id,
                     created_at, updated_at)
                VALUES (:brief_id, :snapshot_id, :workflow_run_id, :title, :narrative,
                        CAST(:source_references AS jsonb), 'PENDING_REVIEW', :mca_run_id,
                        :now, :now)
            """),
                {
                    "brief_id": brief_id,
                    "snapshot_id": snapshot_id,
                    "workflow_run_id": workflow_run_id,
                    "title": command.title,
                    "narrative": narrative,
                    "source_references": json.dumps(source_references),
                    "mca_run_id": agent_run_ids["MCA"],
                    "now": now,
                },
            )
            decision_items = (
                (
                    "RISK",
                    "CRITICAL" if facts["critical_exceptions"] else "HIGH",
                    f"Tinjau {facts['open_exceptions']} exception terbuka",
                    "facts.open_exceptions",
                    facts["open_exceptions"],
                ),
                (
                    "CAPA",
                    "HIGH",
                    f"Tinjau {facts['active_capas']} CAPA aktif",
                    "facts.active_capas",
                    facts["active_capas"],
                ),
                (
                    "APPROVAL",
                    "HIGH",
                    f"Tinjau {facts['pending_approvals']} approval tertunda",
                    "facts.pending_approvals",
                    facts["pending_approvals"],
                ),
            )
            decision_item_count = 0
            for category, priority, title, source_path, count in decision_items:
                if count == 0:
                    continue
                connection.execute(
                    text("""
                    INSERT INTO executive.decision_items
                        (executive_brief_id, category, priority, title, source_path,
                         status, created_at)
                    VALUES (:brief_id, :category, :priority, :title, :source_path,
                            'OPEN', :now)
                """),
                    {
                        "brief_id": brief_id,
                        "category": category,
                        "priority": priority,
                        "title": title,
                        "source_path": source_path,
                        "now": now,
                    },
                )
                decision_item_count += 1
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = 'brief-review',
                    version = version + 1 WHERE workflow_run_id = :run_id
            """),
                {"run_id": workflow_run_id},
            )
            self._append_audit(
                connection,
                principal,
                "executive.brief_generated",
                "executive_brief",
                brief_id,
                correlation_id,
                None,
                {
                    "snapshot_id": str(snapshot_id),
                    "source_hash": source_hash,
                    "decision_item_count": decision_item_count,
                },
            )
        return ExecutiveBriefResult(
            executive_brief_id=brief_id,
            executive_snapshot_id=snapshot_id,
            workflow_run_id=workflow_run_id,
            current_step="brief-review",
            workflow_status="ACTIVE",
            brief_status="PENDING_REVIEW",
            title=command.title,
            summary_counts=facts,
            narrative=narrative,
            source_references=source_references,
            decision_item_count=decision_item_count,
            terminal=False,
            correlation_id=correlation_id,
        )

    def review_executive_brief(
        self,
        executive_brief_id: UUID,
        command: ExecutiveBriefReviewCreate,
        principal: Principal,
        definition: WorkflowDefinition,
    ) -> ExecutiveBriefResult:
        now, machine = datetime.now(UTC), StateMachine(definition)
        with self._engine.begin() as connection:
            context = self._load_executive_brief(connection, executive_brief_id, principal)
            if context["current_step"] != "brief-review" or context["status"] != "PENDING_REVIEW":
                raise ValueError("Executive Brief tidak menunggu review Direktur")
            reviewer_exists = connection.execute(
                text("""
                    SELECT 1 FROM identity.users
                    WHERE user_id = :id AND organization_id = :organization_id
                      AND status = 'ACTIVE'
                """),
                {"id": principal.user_id, "organization_id": principal.organization_id},
            ).first()
            if reviewer_exists is None:
                raise AuthorizationDenied("Direktur belum diprovisikan")
            outcome = "published" if command.decision == "PUBLISHED" else "revision_requested"
            transition = machine.transition("brief-review", outcome)
            exception_id: UUID | None = None
            if command.decision == "REVISION_REQUESTED":
                exception_id = uuid4()
                connection.execute(
                    text("""
                    INSERT INTO governance.exceptions
                        (exception_id, organization_id, work_item_id, category, severity, status,
                         owner_user_id, due_at, created_at)
                    VALUES (:exception_id, :organization_id, NULL,
                            'EXECUTIVE_BRIEF_REVISION', 'HIGH',
                            'OPEN', :owner, :due_at, :now)
                """),
                    {
                        "exception_id": exception_id,
                        "organization_id": principal.organization_id,
                        "owner": principal.user_id,
                        "due_at": now + timedelta(days=2),
                        "now": now,
                    },
                )
            connection.execute(
                text("""
                UPDATE executive.briefs
                SET status = :status, reviewer_user_id = :reviewer,
                    review_notes = :notes, reviewed_at = :now, updated_at = :now,
                    version = version + 1
                WHERE executive_brief_id = :brief_id
            """),
                {
                    "status": command.decision,
                    "reviewer": principal.user_id,
                    "notes": command.notes,
                    "now": now,
                    "brief_id": executive_brief_id,
                },
            )
            connection.execute(
                text("""
                UPDATE workflow.workflow_runs SET current_step = :step,
                    status = 'COMPLETED', completed_at = :now, version = version + 1
                WHERE workflow_run_id = :workflow_run_id
            """),
                {
                    "step": transition.current_step,
                    "now": now,
                    "workflow_run_id": context["workflow_run_id"],
                },
            )
            self._record_transition(
                connection,
                context["workflow_run_id"],
                transition,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._append_audit(
                connection,
                principal,
                "executive.brief_reviewed",
                "executive_brief",
                executive_brief_id,
                context["correlation_id"],
                {"status": context["status"]},
                {
                    "status": command.decision,
                    "exception_id": str(exception_id) if exception_id else None,
                },
            )
            decision_item_count = connection.execute(
                text("""
                SELECT count(*) FROM executive.decision_items
                WHERE executive_brief_id = :brief_id
            """),
                {"brief_id": executive_brief_id},
            ).scalar_one()
            return ExecutiveBriefResult(
                executive_brief_id=executive_brief_id,
                executive_snapshot_id=context["executive_snapshot_id"],
                workflow_run_id=context["workflow_run_id"],
                current_step=transition.current_step,
                workflow_status="COMPLETED",
                brief_status=command.decision,
                title=context["title"],
                summary_counts=context["facts"],
                narrative=context["narrative"],
                source_references=context["source_references"],
                decision_item_count=decision_item_count,
                exception_id=exception_id,
                terminal=True,
                correlation_id=context["correlation_id"],
            )

    @staticmethod
    def _executive_counts(
        connection: Any, principal: Principal, command: ExecutiveBriefCreate
    ) -> dict[str, int]:
        parameters = {
            "organization_id": principal.organization_id,
            "project_id": command.project_id,
            "period_start": command.period_start,
            "period_end": command.period_end,
        }

        def count(query: str) -> int:
            return int(connection.execute(text(query), parameters).scalar_one())

        facts = {
            "active_work_items": count(
                """
                SELECT count(*) FROM platform.work_items wi
                WHERE wi.organization_id = :organization_id
                  AND wi.status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND wi.created_at >= CAST(:period_start AS date)
                  AND wi.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "pending_approvals": count(
                """
                SELECT count(*) FROM governance.approval_requests ar
                JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
                WHERE wi.organization_id = :organization_id AND ar.status = 'PENDING'
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND ar.created_at >= CAST(:period_start AS date)
                  AND ar.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "open_exceptions": count(
                """
                SELECT count(*) FROM governance.exceptions e
                LEFT JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
                WHERE e.organization_id = :organization_id
                  AND e.status IN ('OPEN', 'INVESTIGATING', 'CAPA_REQUIRED')
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND e.created_at >= CAST(:period_start AS date)
                  AND e.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "critical_exceptions": count(
                """
                SELECT count(*) FROM governance.exceptions e
                LEFT JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
                WHERE e.organization_id = :organization_id AND e.severity = 'CRITICAL'
                  AND e.status IN ('OPEN', 'INVESTIGATING', 'CAPA_REQUIRED')
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND e.created_at >= CAST(:period_start AS date)
                  AND e.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "active_capas": count(
                """
                SELECT count(*) FROM governance.capas c
                JOIN governance.exceptions e ON e.exception_id = c.exception_id
                LEFT JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
                WHERE e.organization_id = :organization_id AND c.status <> 'CLOSED'
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND c.created_at >= CAST(:period_start AS date)
                  AND c.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "verified_kpi_snapshots": count(
                """
                SELECT count(*) FROM executive.kpi_snapshots k
                WHERE k.organization_id = :organization_id
                  AND k.verification_status = 'VERIFIED'
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR k.project_id = CAST(:project_id AS uuid))
                  AND k.created_at >= CAST(:period_start AS date)
                  AND k.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "sales_records": count(
                """
                SELECT count(*) FROM sales.leads l
                JOIN platform.work_items wi ON wi.work_item_id = l.work_item_id
                WHERE wi.organization_id = :organization_id
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR wi.project_id = CAST(:project_id AS uuid))
                  AND l.created_at >= CAST(:period_start AS date)
                  AND l.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "finance_records": count(
                """
                SELECT count(*) FROM finance.payment_requests f
                WHERE f.organization_id = :organization_id
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR f.project_id = CAST(:project_id AS uuid))
                  AND f.created_at >= CAST(:period_start AS date)
                  AND f.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "property_records": count(
                """
                SELECT count(*) FROM property.site_evidence p
                WHERE p.organization_id = :organization_id
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR p.project_id = CAST(:project_id AS uuid))
                  AND p.created_at >= CAST(:period_start AS date)
                  AND p.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "legal_records": count(
                """
                SELECT count(*) FROM legal.cases l
                WHERE l.organization_id = :organization_id
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR l.project_id = CAST(:project_id AS uuid))
                  AND l.created_at >= CAST(:period_start AS date)
                  AND l.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
            "hr_records": count(
                """
                SELECT count(*) FROM hr.recruitment_requests h
                WHERE h.organization_id = :organization_id
                  AND (CAST(:project_id AS uuid) IS NULL
                       OR h.project_id = CAST(:project_id AS uuid))
                  AND h.created_at >= CAST(:period_start AS date)
                  AND h.created_at < CAST(:period_end AS date) + INTERVAL '1 day'
                """
            ),
        }
        return facts

    @staticmethod
    def _executive_narrative(command: ExecutiveBriefCreate, facts: Mapping[str, int]) -> str:
        scope = f"project {command.project_id}" if command.project_id else "seluruh organisasi"
        return (
            f"Brief {scope} untuk {command.period_start} sampai {command.period_end}. "
            f"Terdapat {facts['active_work_items']} work item aktif, "
            f"{facts['pending_approvals']} approval tertunda, "
            f"{facts['open_exceptions']} exception terbuka, dan "
            f"{facts['active_capas']} CAPA aktif. Catatan domain pada periode ini: "
            f"Sales {facts['sales_records']}, Finance {facts['finance_records']}, "
            f"Property {facts['property_records']}, Legal {facts['legal_records']}, "
            f"dan HR {facts['hr_records']}. Seluruh angka berasal dari snapshot ALOS "
            "dan memerlukan review Direktur sebelum diterbitkan."
        )

    @staticmethod
    def _load_executive_brief(
        connection: Any, executive_brief_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
                SELECT b.executive_brief_id, b.executive_snapshot_id, b.workflow_run_id,
                       b.title, b.narrative, b.source_references, b.status,
                       s.project_id, s.facts, wr.current_step, wr.correlation_id
                FROM executive.briefs b
                JOIN executive.snapshots s
                  ON s.executive_snapshot_id = b.executive_snapshot_id
                JOIN workflow.workflow_runs wr ON wr.workflow_run_id = b.workflow_run_id
                WHERE b.executive_brief_id = :brief_id
                  AND s.organization_id = :organization_id
                FOR UPDATE OF b, wr
            """),
                {
                    "brief_id": executive_brief_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Executive Brief tidak ditemukan")
        if row["project_id"] is not None and not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke scope Executive Brief")
        return cast(Mapping[str, Any], row)

    def create_project(self, command: ProjectCreate, principal: Principal) -> ProjectView:
        project_id = uuid4()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    INSERT INTO platform.projects
                        (project_id, organization_id, code, name, status, created_at, updated_at)
                    VALUES (:project_id, :organization_id, :code, :name, 'DRAFT', :now, :now)
                    RETURNING project_id, organization_id, code, name, status, created_at
                    """
                    ),
                    {
                        "project_id": project_id,
                        "organization_id": principal.organization_id,
                        "code": command.code,
                        "name": command.name,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            self._append_audit(
                connection,
                principal,
                "project.created",
                "project",
                project_id,
                project_id,
                None,
                dict(row),
            )
        return ProjectView.model_validate(dict(row))

    def update_project_status(
        self, project_id: UUID, command: ProjectStatusUpdate, principal: Principal
    ) -> ProjectView:
        allowed_transitions = {
            "DRAFT": {"ACTIVE"},
            "ACTIVE": {"ON_HOLD", "CLOSED"},
            "ON_HOLD": {"ACTIVE", "CLOSED"},
            "CLOSED": set(),
        }
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            current = (
                connection.execute(
                    text(
                        """
                        SELECT project_id, organization_id, code, name, status, created_at
                        FROM platform.projects
                        WHERE project_id = :project_id
                          AND organization_id = :organization_id
                        FOR UPDATE
                        """
                    ),
                    {
                        "project_id": project_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                raise KeyError("Proyek tidak ditemukan")
            current_status = str(current["status"])
            target_status = command.status.value
            if target_status not in allowed_transitions[current_status]:
                raise ValueError(
                    f"Transisi status proyek {current_status} ke {target_status} tidak diizinkan"
                )
            updated = (
                connection.execute(
                    text(
                        """
                        UPDATE platform.projects
                        SET status = :status, updated_at = :now, version = version + 1
                        WHERE project_id = :project_id
                        RETURNING project_id, organization_id, code, name, status, created_at
                        """
                    ),
                    {"project_id": project_id, "status": target_status, "now": now},
                )
                .mappings()
                .one()
            )
            self._append_audit(
                connection,
                principal,
                "project.status_changed",
                "project",
                project_id,
                project_id,
                dict(current),
                {**dict(updated), "reason": command.reason},
            )
        return ProjectView.model_validate(dict(updated))

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]:
        parameters: dict[str, Any] = {"organization_id": principal.organization_id}
        organization_wide = principal.has_any_role(*self._organization_wide_roles())
        if not organization_wide:
            if not principal.project_ids:
                return ()
            parameters["project_ids"] = list(principal.project_ids)
        with self._engine.connect() as connection:
            if organization_wide:
                query = text("""
                    SELECT project_id, organization_id, code, name, status, created_at
                    FROM platform.projects
                    WHERE organization_id = :organization_id
                    ORDER BY code
                """)
            else:
                query = text("""
                    SELECT project_id, organization_id, code, name, status, created_at
                    FROM platform.projects
                    WHERE organization_id = :organization_id
                      AND project_id = ANY(CAST(:project_ids AS uuid[]))
                    ORDER BY code
                """)
            rows = connection.execute(query, parameters).mappings()
            return tuple(ProjectView.model_validate(dict(row)) for row in rows)

    def create_lead(
        self,
        command: LeadIntake,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> LeadIntakeResult:
        lead_id = uuid4()
        work_item_id = uuid4()
        workflow_run_id = uuid4()
        now = datetime.now(UTC)
        due_at = now + timedelta(minutes=15)
        machine = StateMachine(definition)
        lead_valid = bool(
            agent_plan.execution is not None
            and agent_plan.execution.output_reference.get("valid") is True
        )
        current_step = "sales-assignment" if lead_valid else "exception-open"
        work_item_status = (
            WorkItemStatus.NEEDS_REVIEW if lead_valid else WorkItemStatus.BLOCKED
        )
        lead_status = "VALIDATED" if lead_valid else "EXCEPTION"
        pipeline_stage = "QUALIFICATION" if lead_valid else "EXCEPTION"
        workflow_status = "ACTIVE" if lead_valid else "COMPLETED"
        if not lead_valid:
            due_at = now + timedelta(hours=24)
        operation = "sales.lead.create"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            self._assert_project(connection, command.project_id, principal)
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return LeadIntakeResult.model_validate(receipt)
            duplicate_lead = connection.execute(
                text(
                    """
                    SELECT lead_id
                    FROM sales.leads
                    WHERE organization_id = :organization_id
                      AND project_id = :project_id
                      AND (
                        (CAST(:phone AS text) IS NOT NULL AND phone = CAST(:phone AS text))
                        OR (
                          CAST(:email AS text) IS NOT NULL
                          AND lower(email) = lower(CAST(:email AS text))
                        )
                      )
                    LIMIT 1
                    """
                ),
                {
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "phone": command.phone,
                    "email": command.email,
                },
            ).first()
            if duplicate_lead is not None:
                raise ValueError("Lead dengan kontak yang sama sudah terdaftar pada proyek")

            division_id = connection.execute(
                text(
                    """
                    SELECT division_id FROM identity.divisions
                    WHERE organization_id = :organization_id AND code = 'SALES_MARKETING'
                    """
                ),
                {"organization_id": principal.organization_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO platform.work_items
                        (work_item_id, organization_id, project_id, division_id, title,
                         work_type, priority, status, due_at, correlation_id, created_at,
                         updated_at)
                    VALUES
                        (:work_item_id, :organization_id, :project_id, :division_id, :title,
                         'LEAD_INTAKE', :priority, :status, :due_at, :correlation_id,
                         :now, :now)
                    """
                ),
                {
                    "work_item_id": work_item_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "division_id": division_id,
                    "title": f"Tindak lanjut lead: {command.full_name}",
                    "priority": command.priority.value,
                    "status": work_item_status.value,
                    "due_at": due_at,
                    "correlation_id": correlation_id,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO sales.leads
                        (lead_id, organization_id, project_id, work_item_id, full_name,
                         phone, email, source, consent_recorded, status, pipeline_stage,
                         created_at)
                    VALUES
                        (:lead_id, :organization_id, :project_id, :work_item_id, :full_name,
                         :phone, :email, :source, :consent_recorded, :status,
                          :pipeline_stage, :now)
                    """
                ),
                {
                    "lead_id": lead_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "work_item_id": work_item_id,
                    "full_name": command.full_name,
                    "phone": command.phone,
                    "email": command.email,
                    "source": command.source,
                    "consent_recorded": command.consent_recorded,
                    "status": lead_status,
                    "pipeline_stage": pipeline_stage,
                    "now": now,
                },
            )
            workflow_release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text(
                    """
                    INSERT INTO workflow.workflow_runs
                        (workflow_run_id, workflow_release_id, work_item_id, current_step,
                         status, correlation_id, idempotency_key, started_at, completed_at)
                    VALUES
                        (:run_id, :release_id, :work_item_id, :current_step, :status,
                         :correlation_id, :idempotency_key, :now, :completed_at)
                    """
                ),
                {
                    "run_id": workflow_run_id,
                    "release_id": workflow_release_id,
                    "work_item_id": work_item_id,
                    "current_step": current_step,
                    "status": workflow_status,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                    "completed_at": None if lead_valid else now,
                },
            )
            self._record_agent_run(
                connection,
                agent_plan,
                workflow_run_id,
                correlation_id,
                {
                    "result": "VALIDATED" if lead_valid else "INVALID",
                    "next_step": current_step,
                },
                now,
            )
            received = machine.transition("lead-received", "submitted")
            validation = machine.transition(
                received.current_step, "valid" if lead_valid else "invalid"
            )
            self._record_transition(
                connection,
                workflow_run_id,
                received,
                "HUMAN",
                principal.user_id,
                now,
            )
            self._record_transition(
                connection, workflow_run_id, validation, "AGENT", "SLA", now
            )
            if not lead_valid:
                connection.execute(
                    text("""
                        INSERT INTO governance.exceptions
                            (organization_id, work_item_id, category, severity, status,
                             owner_user_id, due_at, created_at)
                        VALUES (:organization_id, :work_item_id, 'LEAD_VALIDATION_FAILED',
                                'MEDIUM', 'OPEN', :owner, :due_at, :now)
                    """),
                    {
                        "organization_id": principal.organization_id,
                        "work_item_id": work_item_id,
                        "owner": principal.user_id,
                        "due_at": due_at,
                        "now": now,
                    },
                )
            self._append_audit(
                connection,
                principal,
                "lead.intake_validated" if lead_valid else "lead.intake_exception_opened",
                "lead",
                lead_id,
                correlation_id,
                None,
                {
                    "work_item_id": str(work_item_id),
                    "workflow_run_id": str(workflow_run_id),
                    "current_step": current_step,
                    "valid": lead_valid,
                },
            )
            result = LeadIntakeResult(
                lead_id=lead_id,
                work_item_id=work_item_id,
                workflow_run_id=workflow_run_id,
                current_step=current_step,
                work_item_status=work_item_status,
                due_at=due_at,
                correlation_id=correlation_id,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "lead",
                lead_id,
                result.model_dump(mode="json"),
            )
        return result

    def list_work_items(
        self, principal: Principal, project_id: UUID | None
    ) -> tuple[WorkItemView, ...]:
        organization_wide = principal.has_any_role(*self._business_wide_roles())
        if not organization_wide and not principal.division_codes:
            return ()
        if not organization_wide and project_id is None and not principal.project_ids:
            return ()
        parameters: dict[str, Any] = {
            "organization_id": principal.organization_id,
            "project_id": project_id,
            "organization_wide": organization_wide,
            "division_codes": list(principal.division_codes),
            "project_ids": [str(value) for value in principal.project_ids],
        }
        query = text("""
            SELECT wi.work_item_id, wi.organization_id, wi.project_id, d.code AS division_code,
                   wi.title, wi.work_type, wi.priority, wi.status, wi.owner_user_id,
                   wi.due_at, wi.correlation_id, wi.created_at
            FROM platform.work_items wi
            JOIN identity.divisions d ON d.division_id = wi.division_id
            WHERE wi.organization_id = :organization_id
              AND (CAST(:project_id AS uuid) IS NULL OR wi.project_id = :project_id)
              AND (CAST(:organization_wide AS boolean)
                   OR d.code = ANY(CAST(:division_codes AS text[])))
              AND (
                  CAST(:project_id AS uuid) IS NOT NULL
                  OR CAST(:organization_wide AS boolean)
                  OR wi.project_id = ANY(CAST(:project_ids AS uuid[]))
              )
            ORDER BY wi.due_at NULLS LAST, wi.created_at
        """)
        with self._engine.connect() as connection:
            rows = connection.execute(query, parameters).mappings()
            return tuple(WorkItemView.model_validate(dict(row)) for row in rows)

    def assign_sales_pic(
        self,
        workflow_run_id: UUID,
        command: SalesAssignment,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
        idempotency_key: str,
    ) -> WorkflowActionResult:
        machine = StateMachine(definition)
        now = datetime.now(UTC)
        due_at = command.first_follow_up_at or now + timedelta(hours=24)
        if due_at <= now:
            raise ValueError("Jadwal follow-up harus berada di masa depan")
        operation = f"sales.lead.assign:{workflow_run_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
            if (
                command.sales_pic_user_id != principal.user_id
                and not principal.has_any_role(Role.DIVISION_HEAD)
            ):
                raise AuthorizationDenied(
                    "Sales hanya dapat menerima assignment untuk dirinya sendiri; "
                    "penugasan PIC lain memerlukan Kepala Sales"
                )
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return WorkflowActionResult.model_validate(receipt)
            if context["current_step"] != "sales-assignment":
                raise ValueError("Workflow tidak berada pada langkah sales-assignment")
            eligible = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM identity.users u
                    JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                    JOIN identity.divisions d ON d.division_id = ra.division_id
                    WHERE u.user_id = :user_id
                      AND u.organization_id = :organization_id
                      AND u.status = 'ACTIVE'
                      AND d.organization_id = :organization_id
                      AND d.code = 'SALES_MARKETING'
                      AND ra.role_code IN ('SALES', 'DIVISION_HEAD')
                      AND ra.valid_from <= :now
                      AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                      AND EXISTS (
                          SELECT 1 FROM identity.project_assignments pa
                          WHERE pa.user_id = u.user_id
                            AND pa.project_id = :project_id
                            AND pa.valid_from <= :now
                            AND (pa.valid_until IS NULL OR pa.valid_until > :now)
                      )
                    """
                ),
                {
                    "user_id": command.sales_pic_user_id,
                    "organization_id": principal.organization_id,
                    "project_id": context["project_id"],
                    "now": now,
                },
            ).first()
            if eligible is None:
                raise ValueError("Sales PIC tidak aktif atau tidak memiliki role Sales")

            first = machine.transition("sales-assignment", "assigned")
            second = machine.transition(first.current_step, "ready")
            connection.execute(
                text(
                    """
                    UPDATE sales.leads
                    SET assigned_user_id = :owner, status = 'FOLLOW_UP',
                        pipeline_stage = 'FOLLOW_UP', updated_at = :now
                    WHERE lead_id = :lead_id
                    """
                ),
                {"owner": command.sales_pic_user_id, "now": now, "lead_id": context["lead_id"]},
            )
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET owner_user_id = :owner, status = 'NEEDS_REVIEW', due_at = :due_at,
                        updated_at = :now, version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {
                    "owner": command.sales_pic_user_id,
                    "due_at": due_at,
                    "now": now,
                    "work_item_id": context["work_item_id"],
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE workflow.workflow_runs
                    SET current_step = :current_step, version = version + 1
                    WHERE workflow_run_id = :workflow_run_id
                    """
                ),
                {"current_step": second.current_step, "workflow_run_id": workflow_run_id},
            )
            agent_run_id = self._record_agent_run(
                connection,
                agent_plan,
                workflow_run_id,
                context["correlation_id"],
                {
                    "follow_up_due_at": due_at.isoformat(),
                    "assigned_user_id": str(command.sales_pic_user_id),
                },
                now,
            )
            reminder_id = connection.execute(
                text("""
                INSERT INTO platform.reminders
                    (organization_id, work_item_id, recipient_user_id, reminder_type,
                     status, scheduled_for, created_at)
                VALUES (:organization_id, :work_item_id, :recipient, 'FOLLOW_UP',
                        'PENDING', :scheduled_for, :now)
                RETURNING reminder_id
            """),
                {
                    "organization_id": principal.organization_id,
                    "work_item_id": context["work_item_id"],
                    "recipient": command.sales_pic_user_id,
                    "scheduled_for": due_at,
                    "now": now,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO sales.follow_up_tasks
                        (lead_id, workflow_run_id, assigned_user_id, due_at, status,
                         sequence_number, created_by_agent_run_id, reminder_id,
                         objective, idempotency_key, created_at)
                    VALUES
                        (:lead_id, :workflow_run_id, :assigned_user_id, :due_at, 'OPEN',
                         1, :agent_run_id, :reminder_id, :objective, :idempotency_key, :now)
                    """
                ),
                {
                    "lead_id": context["lead_id"],
                    "workflow_run_id": workflow_run_id,
                    "assigned_user_id": command.sales_pic_user_id,
                    "due_at": due_at,
                    "agent_run_id": agent_run_id,
                    "reminder_id": reminder_id,
                    "objective": command.objective,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text("""
                INSERT INTO platform.work_item_assignments
                    (organization_id, work_item_id, from_user_id, to_user_id,
                     action, reason, assigned_by_user_id, assigned_at)
                VALUES (:organization_id, :work_item_id, NULL, :to_user_id,
                        'ASSIGN', :reason, :assigned_by, :now)
            """),
                {
                    "organization_id": principal.organization_id,
                    "work_item_id": context["work_item_id"],
                    "to_user_id": command.sales_pic_user_id,
                    "reason": command.objective,
                    "assigned_by": principal.user_id,
                    "now": now,
                },
            )
            self._record_transition(
                connection, workflow_run_id, first, "HUMAN", principal.user_id, now
            )
            self._record_transition(
                connection, workflow_run_id, second, "AGENT", agent_plan.agent_id, now
            )
            self._append_audit(
                connection,
                principal,
                "sales.pic_assigned",
                "lead",
                context["lead_id"],
                context["correlation_id"],
                {"current_step": "sales-assignment"},
                {
                    "current_step": second.current_step,
                    "sales_pic_user_id": str(command.sales_pic_user_id),
                    "follow_up_due_at": due_at.isoformat(),
                },
            )
            result = self._workflow_result(
                context,
                second.current_step,
                "ACTIVE",
                WorkItemStatus.NEEDS_REVIEW,
                command.sales_pic_user_id,
                due_at,
                second.terminal,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "lead",
                context["lead_id"],
                result.model_dump(mode="json"),
            )
            return result

    def prepare_sales_assignment(
        self,
        workflow_run_id: UUID,
        command: SalesAssignment,
        principal: Principal,
        idempotency_key: str,
    ) -> dict[str, object]:
        """Authorize and validate a Sales assignment before dispatching CFA."""

        now = datetime.now(UTC)
        if command.first_follow_up_at is not None and command.first_follow_up_at <= now:
            raise ValueError("Jadwal follow-up harus berada di masa depan")
        with self._engine.connect() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
            if (
                command.sales_pic_user_id != principal.user_id
                and not principal.has_any_role(Role.DIVISION_HEAD)
            ):
                raise AuthorizationDenied(
                    "Sales hanya dapat menerima assignment untuk dirinya sendiri; "
                    "penugasan PIC lain memerlukan Kepala Sales"
                )
            receipt = self._load_command_receipt(
                connection,
                principal,
                f"sales.lead.assign:{workflow_run_id}",
                idempotency_key,
                command.model_dump(mode="json"),
            )
            if receipt is not None:
                return {"idempotent_replay": True}
            if context["current_step"] != "sales-assignment":
                raise ValueError("Workflow tidak berada pada langkah sales-assignment")
            eligible = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM identity.users u
                    JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                    JOIN identity.divisions d ON d.division_id = ra.division_id
                    WHERE u.user_id = :user_id
                      AND u.organization_id = :organization_id
                      AND u.status = 'ACTIVE'
                      AND d.organization_id = :organization_id
                      AND d.code = 'SALES_MARKETING'
                      AND ra.role_code IN ('SALES', 'DIVISION_HEAD')
                      AND ra.valid_from <= :now
                      AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                      AND EXISTS (
                          SELECT 1 FROM identity.project_assignments pa
                          WHERE pa.user_id = u.user_id
                            AND pa.project_id = :project_id
                            AND pa.valid_from <= :now
                            AND (pa.valid_until IS NULL OR pa.valid_until > :now)
                      )
                    """
                ),
                {
                    "user_id": command.sales_pic_user_id,
                    "organization_id": principal.organization_id,
                    "project_id": context["project_id"],
                    "now": now,
                },
            ).first()
        if eligible is None:
            raise ValueError("Sales PIC tidak aktif atau tidak memiliki role Sales")
        return {"project_id": str(context["project_id"])}

    def prepare_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        idempotency_key: str,
    ) -> dict[str, object]:
        """Authorize a Sales interaction before an optional CFA run is created."""

        with self._engine.connect() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
            if context["owner_user_id"] != principal.user_id and not principal.has_any_role(
                Role.DIVISION_HEAD
            ):
                raise AuthorizationDenied(
                    "Interaksi hanya dapat dicatat Sales PIC yang ditugaskan"
                )
            receipt = self._load_command_receipt(
                connection,
                principal,
                f"sales.lead.interaction:{workflow_run_id}",
                idempotency_key,
                command.model_dump(mode="json"),
            )
            if receipt is not None:
                return {"idempotent_replay": True}
            if context["current_step"] != "interaction-review":
                raise ValueError("Workflow tidak berada pada langkah interaction-review")
        return {
            "owner_user_id": str(context["owner_user_id"]),
            "project_id": str(context["project_id"]),
        }

    def record_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan | None,
        idempotency_key: str,
    ) -> WorkflowActionResult:
        machine = StateMachine(definition)
        now = datetime.now(UTC)
        operation = f"sales.lead.interaction:{workflow_run_id}"
        request_payload = command.model_dump(mode="json")
        with self._engine.begin() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
            if context["owner_user_id"] != principal.user_id and not principal.has_any_role(
                Role.DIVISION_HEAD
            ):
                raise AuthorizationDenied("Interaksi hanya dapat dicatat Sales PIC yang ditugaskan")
            receipt = self._load_command_receipt(
                connection, principal, operation, idempotency_key, request_payload
            )
            if receipt is not None:
                return WorkflowActionResult.model_validate(receipt)
            if context["current_step"] != "interaction-review":
                raise ValueError("Workflow tidak berada pada langkah interaction-review")

            if command.evidence_document_version_id is not None:
                evidence_document = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM platform.document_versions dv
                        JOIN platform.documents d ON d.document_id = dv.document_id
                        WHERE dv.document_version_id = :version_id
                          AND d.organization_id = :organization_id
                          AND (d.project_id IS NULL OR d.project_id = :project_id)
                          AND (
                              d.division_id IS NULL
                              OR d.division_id = (
                                  SELECT division_id FROM identity.divisions
                                  WHERE organization_id = :organization_id
                                    AND code = 'SALES_MARKETING'
                              )
                          )
                          AND dv.verification_status <> 'REJECTED'
                          AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
                        """
                    ),
                    {
                        "version_id": command.evidence_document_version_id,
                        "organization_id": principal.organization_id,
                        "project_id": context["project_id"],
                    },
                ).first()
                if evidence_document is None:
                    raise KeyError("Dokumen evidence Sales tidak ditemukan")

            interaction_id = uuid4()
            connection.execute(
                text(
                    """
                    INSERT INTO sales.interactions
                        (interaction_id, lead_id, workflow_run_id, actor_user_id, channel,
                         outcome, notes, evidence_reference, evidence_document_version_id,
                         qualification_result, lost_reason, next_follow_up_at,
                         idempotency_key, occurred_at)
                    VALUES
                        (:interaction_id, :lead_id, :workflow_run_id, :actor_user_id,
                         :channel, :outcome, :notes, :evidence_reference,
                         :evidence_document_version_id, :qualification_result,
                         :lost_reason, :next_follow_up_at, :idempotency_key, :now)
                    """
                ),
                {
                    "interaction_id": interaction_id,
                    "lead_id": context["lead_id"],
                    "workflow_run_id": workflow_run_id,
                    "actor_user_id": principal.user_id,
                    "channel": command.channel,
                    "outcome": command.outcome.value,
                    "notes": command.notes,
                    "evidence_reference": command.evidence_reference,
                    "evidence_document_version_id": command.evidence_document_version_id,
                    "qualification_result": (
                        command.qualification_result.value
                        if command.qualification_result is not None
                        else ("WARM" if command.outcome == InteractionOutcome.QUALIFIED else None)
                    ),
                    "lost_reason": command.lost_reason,
                    "next_follow_up_at": command.next_follow_up_at,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE sales.follow_up_tasks
                    SET status = 'COMPLETED', completed_at = :now
                    WHERE workflow_run_id = :workflow_run_id AND status = 'OPEN'
                    """
                ),
                {"now": now, "workflow_run_id": workflow_run_id},
            )
            connection.execute(
                text("""
                UPDATE platform.reminders SET status = 'CANCELLED'
                WHERE work_item_id = :work_item_id
                  AND reminder_type = 'FOLLOW_UP' AND status = 'PENDING'
            """),
                {"work_item_id": context["work_item_id"]},
            )
            first = machine.transition("interaction-review", command.outcome.value)
            current_step = first.current_step
            terminal = first.terminal
            due_at: datetime | None = None
            work_status = WorkItemStatus.COMPLETED
            workflow_status = "COMPLETED"
            lead_status = command.outcome.value.upper()
            self._record_transition(
                connection, workflow_run_id, first, "HUMAN", principal.user_id, now
            )

            if command.outcome in {
                InteractionOutcome.FOLLOW_UP,
                InteractionOutcome.QUALIFIED,
            }:
                if agent_plan is None:
                    raise ValueError("CFA execution plan wajib untuk follow-up")
                second = machine.transition(first.current_step, "ready")
                current_step = second.current_step
                terminal = second.terminal
                due_at = command.next_follow_up_at or now + timedelta(hours=24)
                if due_at <= now:
                    raise ValueError("Jadwal follow-up harus berada di masa depan")
                work_status = WorkItemStatus.NEEDS_REVIEW
                workflow_status = "ACTIVE"
                lead_status = (
                    "QUALIFIED"
                    if command.outcome == InteractionOutcome.QUALIFIED
                    else "FOLLOW_UP"
                )
                sequence_number = connection.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(sequence_number), 0) + 1
                        FROM sales.follow_up_tasks WHERE workflow_run_id = :workflow_run_id
                        """
                    ),
                    {"workflow_run_id": workflow_run_id},
                ).scalar_one()
                agent_run_id = self._record_agent_run(
                    connection,
                    agent_plan,
                    workflow_run_id,
                    context["correlation_id"],
                    {"follow_up_due_at": due_at.isoformat(), "sequence": sequence_number},
                    now,
                )
                reminder_id = connection.execute(
                    text("""
                    INSERT INTO platform.reminders
                        (organization_id, work_item_id, recipient_user_id, reminder_type,
                         status, scheduled_for, created_at)
                    VALUES (:organization_id, :work_item_id, :recipient, 'FOLLOW_UP',
                            'PENDING', :scheduled_for, :now)
                    RETURNING reminder_id
                """),
                    {
                        "organization_id": principal.organization_id,
                        "work_item_id": context["work_item_id"],
                        "recipient": context["owner_user_id"],
                        "scheduled_for": due_at,
                        "now": now,
                    },
                ).scalar_one()
                connection.execute(
                    text(
                        """
                        INSERT INTO sales.follow_up_tasks
                            (lead_id, workflow_run_id, assigned_user_id, due_at, status,
                             sequence_number, created_by_agent_run_id, reminder_id,
                             objective, idempotency_key, created_at)
                        VALUES
                            (:lead_id, :workflow_run_id, :assigned_user_id, :due_at, 'OPEN',
                             :sequence_number, :agent_run_id, :reminder_id,
                             :objective, :idempotency_key, :now)
                        """
                    ),
                    {
                        "lead_id": context["lead_id"],
                        "workflow_run_id": workflow_run_id,
                        "assigned_user_id": context["owner_user_id"],
                        "due_at": due_at,
                        "sequence_number": sequence_number,
                        "agent_run_id": agent_run_id,
                        "reminder_id": reminder_id,
                        "objective": command.notes,
                        "idempotency_key": idempotency_key,
                        "now": now,
                    },
                )
                self._record_transition(
                    connection, workflow_run_id, second, "AGENT", agent_plan.agent_id, now
                )
            elif command.outcome == InteractionOutcome.RESERVED:
                connection.execute(
                    text(
                        """
                        INSERT INTO sales.reservations
                            (organization_id, lead_id, workflow_run_id, reservation_reference,
                             recorded_by_user_id, status, evidence_document_version_id,
                             reservation_date, notes, idempotency_key, recorded_at)
                        VALUES
                            (:organization_id, :lead_id, :workflow_run_id, :reference,
                             :actor, 'RECORDED', :evidence_document_version_id,
                             :reservation_date, :notes, :idempotency_key, :now)
                        """
                    ),
                    {
                        "organization_id": principal.organization_id,
                        "lead_id": context["lead_id"],
                        "workflow_run_id": workflow_run_id,
                        "reference": command.reservation_reference,
                        "actor": principal.user_id,
                        "evidence_document_version_id": command.evidence_document_version_id,
                        "reservation_date": command.reservation_date or now.date(),
                        "notes": command.notes,
                        "idempotency_key": idempotency_key,
                        "now": now,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO platform.evidence
                            (evidence_id, work_item_id, document_version_id, claim_type,
                             status, created_at, created_by)
                        VALUES
                            (:evidence_id, :work_item_id, :document_version_id,
                             'RESERVATION_CONFIRMATION', 'SUBMITTED', :now, :actor)
                        """
                    ),
                    {
                        "evidence_id": uuid4(),
                        "work_item_id": context["work_item_id"],
                        "document_version_id": command.evidence_document_version_id,
                        "actor": principal.user_id,
                        "now": now,
                    },
                )
            elif command.outcome == InteractionOutcome.EXCEPTION:
                work_status = WorkItemStatus.BLOCKED
                due_at = now + timedelta(hours=24)
                connection.execute(
                    text(
                        """
                        INSERT INTO governance.exceptions
                            (organization_id, work_item_id, category, severity, status,
                             owner_user_id, due_at, created_at)
                        VALUES
                            (:organization_id, :work_item_id, 'SALES_INTERACTION',
                             'MEDIUM', 'OPEN', :owner, :due_at, :now)
                        """
                    ),
                    {
                        "work_item_id": context["work_item_id"],
                        "organization_id": principal.organization_id,
                        "owner": context["owner_user_id"],
                        "due_at": due_at,
                        "now": now,
                    },
                )

            pipeline_stage = {
                InteractionOutcome.FOLLOW_UP: "FOLLOW_UP",
                InteractionOutcome.QUALIFIED: "QUALIFIED",
                InteractionOutcome.RESERVED: "CONVERTED",
                InteractionOutcome.LOST: "LOST",
                InteractionOutcome.EXCEPTION: "EXCEPTION",
            }[command.outcome]
            connection.execute(
                text(
                    """
                    UPDATE sales.leads
                    SET status = :lead_status, pipeline_stage = :pipeline_stage,
                        qualification_result = COALESCE(:qualification_result,
                                                       qualification_result),
                        qualification_notes = CASE
                            WHEN :is_qualification THEN :notes ELSE qualification_notes END,
                        lost_reason = :lost_reason,
                        converted_at = CASE WHEN :is_reserved THEN :now ELSE converted_at END,
                        lost_at = CASE WHEN :is_lost THEN :now ELSE lost_at END,
                        updated_at = :now
                    WHERE lead_id = :lead_id
                    """
                ),
                {
                    "lead_status": lead_status,
                    "pipeline_stage": pipeline_stage,
                    "qualification_result": (
                        command.qualification_result.value
                        if command.qualification_result is not None
                        else ("WARM" if command.outcome == InteractionOutcome.QUALIFIED else None)
                    ),
                    "is_qualification": command.outcome == InteractionOutcome.QUALIFIED,
                    "notes": command.notes,
                    "lost_reason": command.lost_reason,
                    "is_reserved": command.outcome == InteractionOutcome.RESERVED,
                    "is_lost": command.outcome == InteractionOutcome.LOST,
                    "now": now,
                    "lead_id": context["lead_id"],
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET status = :status, due_at = :due_at, updated_at = :now,
                        version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {
                    "status": work_status.value,
                    "due_at": due_at,
                    "now": now,
                    "work_item_id": context["work_item_id"],
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE workflow.workflow_runs
                    SET current_step = :current_step, status = :status,
                        completed_at = :completed_at, version = version + 1
                    WHERE workflow_run_id = :workflow_run_id
                    """
                ),
                {
                    "current_step": current_step,
                    "status": workflow_status,
                    "completed_at": now if terminal else None,
                    "workflow_run_id": workflow_run_id,
                },
            )
            self._append_audit(
                connection,
                principal,
                "sales.interaction_recorded",
                "lead",
                context["lead_id"],
                context["correlation_id"],
                {"current_step": "interaction-review"},
                {
                    "interaction_id": str(interaction_id),
                    "outcome": command.outcome.value,
                    "current_step": current_step,
                },
            )
            result = self._workflow_result(
                context,
                current_step,
                workflow_status,
                work_status,
                context["owner_user_id"],
                due_at,
                terminal,
            )
            self._save_command_receipt(
                connection,
                principal,
                operation,
                idempotency_key,
                request_payload,
                "lead",
                context["lead_id"],
                result.model_dump(mode="json"),
            )
            return result

    @staticmethod
    def _load_sales_run(
        connection: Any, workflow_run_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text(
                    """
                SELECT wr.workflow_run_id, wr.current_step, wr.status AS workflow_status,
                       wr.correlation_id, wi.work_item_id, wi.project_id, wi.owner_user_id,
                       l.lead_id
                FROM workflow.workflow_runs wr
                JOIN platform.work_items wi ON wi.work_item_id = wr.work_item_id
                JOIN sales.leads l ON l.work_item_id = wi.work_item_id
                WHERE wr.workflow_run_id = :workflow_run_id
                  AND wi.organization_id = :organization_id
                FOR UPDATE OF wr, wi, l
                """
                ),
                {
                    "workflow_run_id": workflow_run_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Workflow Sales tidak ditemukan")
        if not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek workflow")
        return cast(Mapping[str, Any], row)

    def _record_agent_run(
        self,
        connection: Any,
        plan: AgentExecutionPlan,
        workflow_run_id: UUID,
        correlation_id: UUID,
        output: Mapping[str, Any],
        occurred_at: datetime,
    ) -> UUID:
        release_id = self._upsert_agent_release(connection, plan)
        execution = plan.execution
        persisted_output = dict(output)
        if execution is not None:
            persisted_output["_runtime"] = {
                "handler_id": execution.handler_id,
                "result": execution.output_reference,
                "verification_status": execution.verification_status.value,
            }
        status = execution.status.value if execution is not None else "COMPLETED"
        evidence_references = execution.evidence_references if execution is not None else ()
        warnings = execution.warnings if execution is not None else ()
        provider_metadata = execution.provider_metadata if execution is not None else {}
        connection.execute(
            text(
                """
                INSERT INTO agents.agent_runs
                    (agent_run_id, agent_release_id, workflow_run_id, status,
                     input_reference, output_reference, correlation_id,
                     idempotency_key, started_at, completed_at, capability,
                     capability_version, capability_contract_digest,
                     execution_mode, approved_tools, workflow_step_id, contract_digest,
                     handler_id, evidence_references, warnings, verification_status,
                     provider_metadata)
                VALUES
                    (:agent_run_id, :release_id, :workflow_run_id, :status,
                     CAST(:inputs AS jsonb), CAST(:output AS jsonb), :correlation_id,
                     :idempotency_key, :occurred_at, :occurred_at, :capability,
                     :capability_version, :capability_contract_digest,
                     :execution_mode, CAST(:approved_tools AS jsonb), :workflow_step_id,
                     :contract_digest, :handler_id, CAST(:evidence_references AS jsonb),
                     CAST(:warnings AS jsonb), :verification_status,
                     CAST(:provider_metadata AS jsonb))
                """
            ),
            {
                "agent_run_id": plan.run_id,
                "release_id": release_id,
                "workflow_run_id": workflow_run_id,
                "inputs": json.dumps(plan.input_references),
                "output": json.dumps(persisted_output),
                "status": status,
                "correlation_id": correlation_id,
                "idempotency_key": plan.idempotency_key,
                "occurred_at": occurred_at,
                "capability": plan.capability,
                "capability_version": plan.capability_version,
                "capability_contract_digest": plan.capability_contract_digest,
                "execution_mode": plan.execution_mode.value,
                "approved_tools": json.dumps(
                    [item.model_dump(mode="json") for item in plan.approved_tool_releases]
                ),
                "workflow_step_id": plan.workflow_step_id,
                "contract_digest": plan.contract_digest,
                "handler_id": execution.handler_id if execution is not None else None,
                "evidence_references": json.dumps(evidence_references),
                "warnings": json.dumps(warnings),
                "verification_status": (
                    execution.verification_status.value if execution is not None else None
                ),
                "provider_metadata": json.dumps(provider_metadata),
            },
        )
        return plan.run_id

    @staticmethod
    def _record_transition(
        connection: Any,
        workflow_run_id: UUID,
        result: Any,
        actor_type: str,
        actor_id: object,
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO workflow.transition_events
                    (workflow_run_id, from_step, outcome, to_step, actor_type,
                     actor_id, occurred_at)
                VALUES
                    (:workflow_run_id, :from_step, :outcome, :to_step, :actor_type,
                     :actor_id, :occurred_at)
                """
            ),
            {
                "workflow_run_id": workflow_run_id,
                "from_step": result.previous_step,
                "outcome": result.outcome,
                "to_step": result.current_step,
                "actor_type": actor_type,
                "actor_id": str(actor_id),
                "occurred_at": occurred_at,
            },
        )

    @staticmethod
    def _workflow_result(
        context: Mapping[str, Any],
        current_step: str,
        workflow_status: str,
        work_item_status: WorkItemStatus,
        owner_user_id: UUID | None,
        due_at: datetime | None,
        terminal: bool,
    ) -> WorkflowActionResult:
        return WorkflowActionResult(
            workflow_run_id=context["workflow_run_id"],
            work_item_id=context["work_item_id"],
            lead_id=context["lead_id"],
            current_step=current_step,
            workflow_status=workflow_status,
            work_item_status=work_item_status,
            owner_user_id=owner_user_id,
            due_at=due_at,
            terminal=terminal,
            correlation_id=context["correlation_id"],
        )

    def _payment_approval_route(self, amount: Decimal) -> tuple[str, str, int]:
        tier = self._payment_approval_policy.route_for(amount)
        return tier.route, tier.required_role, tier.sla_hours

    @staticmethod
    def _assert_payment_approver(
        context: Mapping[str, Any], principal: Principal
    ) -> None:
        assigned = context.get("assigned_approver_user_id")
        if assigned is not None and assigned != principal.user_id:
            raise AuthorizationDenied("Approval telah ditugaskan kepada approver lain")
        required_role = context.get("required_role_code")
        finance_scope = "FINANCE" in principal.division_codes
        allowed = False
        if required_role == "FINANCE":
            allowed = finance_scope and principal.has_any_role(Role.FINANCE, Role.DIVISION_HEAD)
        elif required_role == "DIVISION_HEAD":
            allowed = finance_scope and principal.has_any_role(Role.DIVISION_HEAD)
        elif required_role == "DIRECTOR":
            allowed = principal.has_any_role(Role.DIRECTOR)
        if not allowed:
            raise AuthorizationDenied(
                f"Jalur approval memerlukan peran {required_role or 'yang ditetapkan'}"
            )

    @staticmethod
    def _load_payment(
        connection: Any, payment_request_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
            SELECT pr.payment_request_id, pr.work_item_id, pr.workflow_run_id,
                   pr.approval_request_id, pr.requester_user_id, pr.project_id,
                   pr.budget_id, pr.amount, pr.currency, pr.requested_payment_date, pr.status,
                   pr.revision_number, wr.current_step, wr.correlation_id,
                   ar.required_role_code, ar.required_division_code,
                   ar.assigned_approver_user_id
            FROM finance.payment_requests pr
            JOIN workflow.workflow_runs wr ON wr.workflow_run_id = pr.workflow_run_id
            LEFT JOIN governance.approval_requests ar
              ON ar.approval_request_id = pr.approval_request_id
            WHERE pr.payment_request_id = :payment_request_id
              AND pr.organization_id = :organization_id
            FOR UPDATE OF pr, wr
        """),
                {
                    "payment_request_id": payment_request_id,
                    "organization_id": principal.organization_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Payment request tidak ditemukan")
        if not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke payment request")
        return cast(Mapping[str, Any], row)

    @staticmethod
    def _update_payment_state(
        connection: Any,
        context: Mapping[str, Any],
        current_step: str,
        payment_status: str,
        work_status: str,
        terminal: bool,
        now: datetime,
    ) -> None:
        connection.execute(
            text("""
            UPDATE finance.payment_requests SET status = :status, updated_at = :now,
                version = version + 1 WHERE payment_request_id = :payment_request_id
        """),
            {
                "status": payment_status,
                "now": now,
                "payment_request_id": context["payment_request_id"],
            },
        )
        connection.execute(
            text("""
            UPDATE platform.work_items SET status = :status, updated_at = :now,
                version = version + 1 WHERE work_item_id = :work_item_id
        """),
            {"status": work_status, "now": now, "work_item_id": context["work_item_id"]},
        )
        connection.execute(
            text("""
            UPDATE workflow.workflow_runs SET current_step = :step, status = :status,
                completed_at = :completed_at, version = version + 1
            WHERE workflow_run_id = :workflow_run_id
        """),
            {
                "step": current_step,
                "status": "COMPLETED" if terminal else "ACTIVE",
                "completed_at": now if terminal else None,
                "workflow_run_id": context["workflow_run_id"],
            },
        )

    @staticmethod
    def _finance_result(
        context: Mapping[str, Any],
        current_step: str,
        payment_status: str,
        work_item_status: str,
        terminal: bool,
        reconciliation_status: str | None = None,
        difference_amount: Any | None = None,
    ) -> FinanceWorkflowResult:
        return FinanceWorkflowResult(
            payment_request_id=context["payment_request_id"],
            work_item_id=context["work_item_id"],
            workflow_run_id=context["workflow_run_id"],
            approval_request_id=context["approval_request_id"],
            current_step=current_step,
            workflow_status="COMPLETED" if terminal else "ACTIVE",
            payment_status=payment_status,
            work_item_status=WorkItemStatus(work_item_status),
            terminal=terminal,
            correlation_id=context["correlation_id"],
            reconciliation_status=reconciliation_status,
            difference_amount=difference_amount,
        )

    @staticmethod
    def _assert_project(connection: Any, project_id: UUID, principal: Principal) -> None:
        row = connection.execute(
            text("""
                SELECT project_id FROM platform.projects
                WHERE project_id = :project_id AND organization_id = :organization_id
            """),
            {"project_id": project_id, "organization_id": principal.organization_id},
        ).first()
        if row is None or not principal.can_access_project(project_id):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke project")

    @staticmethod
    def _assert_work_item(
        connection: Any, work_item_id: UUID, principal: Principal
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("""
                SELECT wi.work_item_id, wi.project_id, wi.organization_id,
                       d.code AS division_code
                FROM platform.work_items wi
                JOIN identity.divisions d ON d.division_id = wi.division_id
                WHERE wi.work_item_id = :work_item_id
                  AND wi.organization_id = :organization_id
            """),
                {"work_item_id": work_item_id, "organization_id": principal.organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Work item tidak ditemukan")
        if row["project_id"] is not None and not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke work item")
        if (
            not principal.has_any_role(*PostgresOperationalStore._business_wide_roles())
            and row["division_code"] not in principal.division_codes
        ):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke divisi work item")
        return cast(Mapping[str, Any], row)

    @staticmethod
    def _organization_wide_roles() -> tuple[Any, ...]:
        from alos.security import Role

        return (Role.DIRECTOR, Role.AI_EXECUTIVE, Role.IT_ADMIN, Role.AUDITOR)

    @staticmethod
    def _business_wide_roles() -> tuple[Any, ...]:
        """Roles allowed to inspect business records across all divisions."""
        from alos.security import Role

        return (Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR)

    @staticmethod
    def _upsert_workflow_release(connection: Any, definition: WorkflowDefinition) -> UUID:
        release_definition = definition.canonical_payload()
        release_definition["definition_digest"] = definition.definition_digest
        serialized_definition = json.dumps(
            release_definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        release_id = connection.execute(
            text(
                """
                INSERT INTO workflow.workflow_releases
                    (workflow_id, version, definition, status)
                VALUES (:workflow_id, :version, CAST(:definition AS jsonb), :status)
                ON CONFLICT (workflow_id, version)
                DO NOTHING
                RETURNING workflow_release_id
                """
            ),
            {
                "workflow_id": definition.workflow_id,
                "version": definition.version,
                "definition": serialized_definition,
                "status": definition.status,
            },
        ).scalar_one_or_none()
        if release_id is not None:
            return cast(UUID, release_id)

        existing = (
            connection.execute(
                text(
                    """
                    SELECT workflow_release_id, definition
                    FROM workflow.workflow_releases
                    WHERE workflow_id = :workflow_id AND version = :version
                    FOR UPDATE
                    """
                ),
                {"workflow_id": definition.workflow_id, "version": definition.version},
            )
            .mappings()
            .one()
        )
        existing_definition = existing["definition"]
        if existing_definition.get("definition_digest") == definition.definition_digest:
            connection.execute(
                text(
                    """
                    UPDATE workflow.workflow_releases
                    SET status = :status,
                        released_at = CASE
                            WHEN :status = 'RELEASED' THEN COALESCE(released_at, now())
                            ELSE released_at
                        END
                    WHERE workflow_release_id = :workflow_release_id
                    """
                ),
                {
                    "workflow_release_id": existing["workflow_release_id"],
                    "status": definition.status,
                },
            )
            return cast(UUID, existing["workflow_release_id"])

        if "definition_digest" not in existing_definition:
            upgraded_release_id = connection.execute(
                text(
                    """
                    UPDATE workflow.workflow_releases
                    SET definition = CAST(:definition AS jsonb), status = :status
                    WHERE workflow_release_id = :workflow_release_id
                      AND NOT (definition ? 'definition_digest')
                    RETURNING workflow_release_id
                    """
                ),
                {
                    "workflow_release_id": existing["workflow_release_id"],
                    "definition": serialized_definition,
                    "status": definition.status,
                },
            ).scalar_one_or_none()
            if upgraded_release_id is not None:
                return cast(UUID, upgraded_release_id)

        raise WorkflowReleaseConflictError(
            f"Workflow release immutable berbeda untuk "
            f"{definition.workflow_id}@{definition.version}"
        )

    @staticmethod
    def _upsert_agent_release(connection: Any, plan: AgentExecutionPlan) -> UUID:
        definition = plan.contract_snapshot.canonical_payload()
        definition["contract_digest"] = plan.contract_digest
        serialized_definition = json.dumps(
            definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        release_id = connection.execute(
            text(
                """
                INSERT INTO agents.agent_releases
                    (agent_id, version, definition, status)
                VALUES (:agent_id, :version, CAST(:definition AS jsonb), :status)
                ON CONFLICT (agent_id, version)
                DO NOTHING
                RETURNING agent_release_id
                """
            ),
            {
                "agent_id": plan.agent_id,
                "version": plan.agent_version,
                "definition": serialized_definition,
                "status": plan.contract_snapshot.status.value,
            },
        ).scalar_one_or_none()
        if release_id is not None:
            return cast(UUID, release_id)

        existing = (
            connection.execute(
                text(
                    """
                    SELECT agent_release_id, definition
                    FROM agents.agent_releases
                    WHERE agent_id = :agent_id AND version = :version
                    FOR UPDATE
                    """
                ),
                {"agent_id": plan.agent_id, "version": plan.agent_version},
            )
            .mappings()
            .one()
        )
        existing_definition = existing["definition"]
        if existing_definition.get("contract_digest") == plan.contract_digest:
            connection.execute(
                text(
                    """
                    UPDATE agents.agent_releases
                    SET status = :status,
                        released_at = CASE
                            WHEN :status = 'RELEASED' THEN COALESCE(released_at, now())
                            ELSE released_at
                        END
                    WHERE agent_release_id = :agent_release_id
                    """
                ),
                {
                    "agent_release_id": existing["agent_release_id"],
                    "status": plan.contract_snapshot.status.value,
                },
            )
            return cast(UUID, existing["agent_release_id"])

        if "contract_digest" not in existing_definition:
            upgraded_release_id = connection.execute(
                text(
                    """
                    UPDATE agents.agent_releases
                    SET definition = CAST(:definition AS jsonb), status = :status
                    WHERE agent_release_id = :agent_release_id
                      AND NOT (definition ? 'contract_digest')
                    RETURNING agent_release_id
                    """
                ),
                {
                    "agent_release_id": existing["agent_release_id"],
                    "definition": serialized_definition,
                    "status": plan.contract_snapshot.status.value,
                },
            ).scalar_one_or_none()
            if upgraded_release_id is not None:
                return cast(UUID, upgraded_release_id)

        raise AgentReleaseConflictError(
            f"Agent release immutable berbeda untuk {plan.agent_id}@{plan.agent_version}"
        )

    @staticmethod
    def _append_audit(
        connection: Any,
        principal: Principal,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        reason: str | None = None,
    ) -> None:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(CAST(:organization_id AS text)))"),
            {"organization_id": principal.organization_id},
        )
        previous_hash = connection.execute(
            text(
                """
                SELECT candidate.entry_hash
                FROM audit.entries AS candidate
                WHERE candidate.organization_id = :organization_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM audit.entries AS child
                      WHERE child.organization_id = candidate.organization_id
                        AND child.previous_hash = candidate.entry_hash
                  )
                ORDER BY candidate.occurred_at DESC, candidate.audit_entry_id DESC
                LIMIT 1
                FOR UPDATE OF candidate
                """
            ),
            {"organization_id": principal.organization_id},
        ).scalar_one_or_none()
        occurred_at = datetime.now(UTC)
        entry_hash = compute_audit_entry_hash(
            organization_id=principal.organization_id,
            actor_id=str(principal.user_id),
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            correlation_id=correlation_id,
            reason=reason,
            before=before,
            after=after,
            occurred_at=occurred_at,
            previous_hash=previous_hash,
        )
        connection.execute(
            text(
                """
                INSERT INTO audit.entries
                    (organization_id, occurred_at, actor_type, actor_id, active_role,
                     action, entity_type, entity_id, reason, before_masked, after_masked,
                     correlation_id, previous_hash, entry_hash)
                VALUES
                    (:organization_id, :occurred_at, 'HUMAN', :actor_id, :active_role,
                     :action, :entity_type, :entity_id, :reason, CAST(:before AS jsonb),
                     CAST(:after AS jsonb), :correlation_id, :previous_hash, :entry_hash)
                """
            ),
            {
                "organization_id": principal.organization_id,
                "occurred_at": occurred_at,
                "actor_id": str(principal.user_id),
                "active_role": sorted(role.value for role in principal.roles)[0],
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "reason": reason,
                "before": json.dumps(before, default=str) if before is not None else None,
                "after": json.dumps(after, default=str) if after is not None else None,
                "correlation_id": correlation_id,
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
            },
        )
