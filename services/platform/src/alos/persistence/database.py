import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, text

from alos.agents.runtime import AgentExecutionPlan
from alos.platform.models import (
    InteractionOutcome,
    LeadIntake,
    LeadIntakeResult,
    ProjectCreate,
    ProjectView,
    SalesAssignment,
    SalesInteraction,
    WorkflowActionResult,
    WorkItemStatus,
    WorkItemView,
)
from alos.security import Principal, Role, UserCreate, UserView
from alos.security.authorization import AuthorizationDenied
from alos.workflow.models import WorkflowDefinition
from alos.workflow.state_machine import StateMachine


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url, pool_pre_ping=True)


class PostgresOperationalStore:
    def __init__(self, database: Database) -> None:
        self._engine = database.engine

    def create_user(self, command: UserCreate, principal: Principal) -> UserView:
        user_id = uuid4()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
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
                        (user_id, email, display_name, status, created_at, updated_at)
                    VALUES (:user_id, :email, :display_name, 'ACTIVE', :now, :now)
                    """
                ),
                {
                    "user_id": user_id,
                    "email": command.email.lower(),
                    "display_name": command.display_name,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO identity.role_assignments
                        (user_id, division_id, role_code, created_at)
                    VALUES (:user_id, :division_id, :role_code, :now)
                    """
                ),
                {
                    "user_id": user_id,
                    "division_id": division_id,
                    "role_code": command.role.value,
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

    def list_projects(self, principal: Principal) -> tuple[ProjectView, ...]:
        clauses = ["organization_id = :organization_id"]
        parameters: dict[str, Any] = {"organization_id": principal.organization_id}
        if not principal.has_any_role(*self._organization_wide_roles()):
            if not principal.project_ids:
                return ()
            clauses.append("project_id = ANY(CAST(:project_ids AS uuid[]))")
            parameters["project_ids"] = list(principal.project_ids)
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT project_id, organization_id, code, name, status, created_at
                    FROM platform.projects
                    WHERE {" AND ".join(clauses)}
                    ORDER BY code
                    """
                ),
                parameters,
            ).mappings()
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
        with self._engine.begin() as connection:
            project = connection.execute(
                text(
                    """
                    SELECT project_id FROM platform.projects
                    WHERE project_id = :project_id AND organization_id = :organization_id
                    """
                ),
                {
                    "project_id": command.project_id,
                    "organization_id": principal.organization_id,
                },
            ).first()
            if project is None:
                raise KeyError("Proyek tidak ditemukan pada organisasi pengguna")

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
                         'LEAD_INTAKE', :priority, 'NEEDS_REVIEW', :due_at, :correlation_id,
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
                         phone, email, source, consent_recorded, status, created_at)
                    VALUES
                        (:lead_id, :organization_id, :project_id, :work_item_id, :full_name,
                         :phone, :email, :source, :consent_recorded, 'VALIDATED', :now)
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
                    "now": now,
                },
            )
            workflow_release_id = self._upsert_workflow_release(connection, definition)
            connection.execute(
                text(
                    """
                    INSERT INTO workflow.workflow_runs
                        (workflow_run_id, workflow_release_id, work_item_id, current_step,
                         status, correlation_id, idempotency_key, started_at)
                    VALUES
                        (:run_id, :release_id, :work_item_id, 'sales-assignment', 'ACTIVE',
                         :correlation_id, :idempotency_key, :now)
                    """
                ),
                {
                    "run_id": workflow_run_id,
                    "release_id": workflow_release_id,
                    "work_item_id": work_item_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            agent_release_id = self._upsert_agent_release(connection, agent_plan)
            connection.execute(
                text(
                    """
                    INSERT INTO agents.agent_runs
                        (agent_run_id, agent_release_id, workflow_run_id, status,
                         input_reference, output_reference, correlation_id,
                         idempotency_key, started_at, completed_at)
                    VALUES
                        (:agent_run_id, :release_id, :workflow_run_id, 'COMPLETED',
                         CAST(:input_reference AS jsonb), CAST(:output_reference AS jsonb),
                         :correlation_id, :idempotency_key, :now, :now)
                    """
                ),
                {
                    "agent_run_id": agent_plan.run_id,
                    "release_id": agent_release_id,
                    "workflow_run_id": workflow_run_id,
                    "input_reference": json.dumps(agent_plan.input_references),
                    "output_reference": json.dumps(
                        {"result": "VALIDATED", "next_step": "sales-assignment"}
                    ),
                    "correlation_id": correlation_id,
                    "idempotency_key": agent_plan.idempotency_key,
                    "now": now,
                },
            )
            self._append_audit(
                connection,
                principal,
                "lead.intake_validated",
                "lead",
                lead_id,
                correlation_id,
                None,
                {
                    "work_item_id": str(work_item_id),
                    "workflow_run_id": str(workflow_run_id),
                    "current_step": "sales-assignment",
                },
            )
        return LeadIntakeResult(
            lead_id=lead_id,
            work_item_id=work_item_id,
            workflow_run_id=workflow_run_id,
            current_step="sales-assignment",
            work_item_status=WorkItemStatus.NEEDS_REVIEW,
            due_at=due_at,
            correlation_id=correlation_id,
        )

    def list_work_items(
        self, principal: Principal, project_id: UUID | None
    ) -> tuple[WorkItemView, ...]:
        clauses = ["wi.organization_id = :organization_id"]
        parameters: dict[str, Any] = {"organization_id": principal.organization_id}
        if project_id is not None:
            clauses.append("wi.project_id = :project_id")
            parameters["project_id"] = project_id
        if principal.division_codes and not principal.has_any_role(
            *self._organization_wide_roles()
        ):
            clauses.append("d.code = ANY(:division_codes)")
            parameters["division_codes"] = list(principal.division_codes)
        query = f"""
            SELECT wi.work_item_id, wi.organization_id, wi.project_id, d.code AS division_code,
                   wi.title, wi.work_type, wi.priority, wi.status, wi.owner_user_id,
                   wi.due_at, wi.correlation_id, wi.created_at
            FROM platform.work_items wi
            JOIN identity.divisions d ON d.division_id = wi.division_id
            WHERE {" AND ".join(clauses)}
            ORDER BY wi.due_at NULLS LAST, wi.created_at
        """
        with self._engine.connect() as connection:
            rows = connection.execute(text(query), parameters).mappings()
            return tuple(WorkItemView.model_validate(dict(row)) for row in rows)

    def assign_sales_pic(
        self,
        workflow_run_id: UUID,
        command: SalesAssignment,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan,
    ) -> WorkflowActionResult:
        machine = StateMachine(definition)
        now = datetime.now(UTC)
        due_at = now + timedelta(hours=24)
        with self._engine.begin() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
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
                      AND u.status = 'ACTIVE'
                      AND d.organization_id = :organization_id
                      AND d.code = 'SALES_MARKETING'
                      AND ra.role_code IN ('SALES', 'DIVISION_HEAD')
                      AND ra.valid_from <= :now
                      AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                    """
                ),
                {
                    "user_id": command.sales_pic_user_id,
                    "organization_id": principal.organization_id,
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
                    SET assigned_user_id = :owner, status = 'FOLLOW_UP', updated_at = :now
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
            connection.execute(
                text(
                    """
                    INSERT INTO sales.follow_up_tasks
                        (lead_id, workflow_run_id, assigned_user_id, due_at, status,
                         sequence_number, created_by_agent_run_id, created_at)
                    VALUES
                        (:lead_id, :workflow_run_id, :assigned_user_id, :due_at, 'OPEN',
                         1, :agent_run_id, :now)
                    """
                ),
                {
                    "lead_id": context["lead_id"],
                    "workflow_run_id": workflow_run_id,
                    "assigned_user_id": command.sales_pic_user_id,
                    "due_at": due_at,
                    "agent_run_id": agent_run_id,
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
            return self._workflow_result(
                context,
                second.current_step,
                "ACTIVE",
                WorkItemStatus.NEEDS_REVIEW,
                command.sales_pic_user_id,
                due_at,
                second.terminal,
            )

    def record_sales_interaction(
        self,
        workflow_run_id: UUID,
        command: SalesInteraction,
        principal: Principal,
        definition: WorkflowDefinition,
        agent_plan: AgentExecutionPlan | None,
    ) -> WorkflowActionResult:
        machine = StateMachine(definition)
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            context = self._load_sales_run(connection, workflow_run_id, principal)
            if context["current_step"] != "interaction-review":
                raise ValueError("Workflow tidak berada pada langkah interaction-review")
            if context["owner_user_id"] != principal.user_id and not principal.has_any_role(
                Role.DIVISION_HEAD, Role.IT_ADMIN
            ):
                raise AuthorizationDenied("Interaksi hanya dapat dicatat Sales PIC yang ditugaskan")

            interaction_id = uuid4()
            connection.execute(
                text(
                    """
                    INSERT INTO sales.interactions
                        (interaction_id, lead_id, workflow_run_id, actor_user_id, channel,
                         outcome, notes, evidence_reference, occurred_at)
                    VALUES
                        (:interaction_id, :lead_id, :workflow_run_id, :actor_user_id,
                         :channel, :outcome, :notes, :evidence_reference, :now)
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

            if command.outcome == InteractionOutcome.FOLLOW_UP:
                if agent_plan is None:
                    raise ValueError("CFA execution plan wajib untuk follow-up")
                second = machine.transition(first.current_step, "ready")
                current_step = second.current_step
                terminal = second.terminal
                due_at = now + timedelta(hours=24)
                work_status = WorkItemStatus.NEEDS_REVIEW
                workflow_status = "ACTIVE"
                lead_status = "FOLLOW_UP"
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
                connection.execute(
                    text(
                        """
                        INSERT INTO sales.follow_up_tasks
                            (lead_id, workflow_run_id, assigned_user_id, due_at, status,
                             sequence_number, created_by_agent_run_id, created_at)
                        VALUES
                            (:lead_id, :workflow_run_id, :assigned_user_id, :due_at, 'OPEN',
                             :sequence_number, :agent_run_id, :now)
                        """
                    ),
                    {
                        "lead_id": context["lead_id"],
                        "workflow_run_id": workflow_run_id,
                        "assigned_user_id": context["owner_user_id"],
                        "due_at": due_at,
                        "sequence_number": sequence_number,
                        "agent_run_id": agent_run_id,
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
                            (lead_id, workflow_run_id, reservation_reference,
                             recorded_by_user_id, status, recorded_at)
                        VALUES
                            (:lead_id, :workflow_run_id, :reference, :actor, 'RECORDED', :now)
                        """
                    ),
                    {
                        "lead_id": context["lead_id"],
                        "workflow_run_id": workflow_run_id,
                        "reference": command.reservation_reference,
                        "actor": principal.user_id,
                        "now": now,
                    },
                )
            elif command.outcome == InteractionOutcome.EXCEPTION:
                work_status = WorkItemStatus.BLOCKED
                connection.execute(
                    text(
                        """
                        INSERT INTO governance.exceptions
                            (work_item_id, category, severity, status, owner_user_id, created_at)
                        VALUES
                            (:work_item_id, 'SALES_INTERACTION', 'MEDIUM', 'OPEN', :owner, :now)
                        """
                    ),
                    {
                        "work_item_id": context["work_item_id"],
                        "owner": context["owner_user_id"],
                        "now": now,
                    },
                )

            connection.execute(
                text(
                    """
                    UPDATE sales.leads
                    SET status = :lead_status, updated_at = :now
                    WHERE lead_id = :lead_id
                    """
                ),
                {"lead_status": lead_status, "now": now, "lead_id": context["lead_id"]},
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
            return self._workflow_result(
                context,
                current_step,
                workflow_status,
                work_status,
                context["owner_user_id"],
                due_at,
                terminal,
            )

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
        return row

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
        connection.execute(
            text(
                """
                INSERT INTO agents.agent_runs
                    (agent_run_id, agent_release_id, workflow_run_id, status,
                     input_reference, output_reference, correlation_id,
                     idempotency_key, started_at, completed_at)
                VALUES
                    (:agent_run_id, :release_id, :workflow_run_id, 'COMPLETED',
                     CAST(:inputs AS jsonb), CAST(:output AS jsonb), :correlation_id,
                     :idempotency_key, :occurred_at, :occurred_at)
                """
            ),
            {
                "agent_run_id": plan.run_id,
                "release_id": release_id,
                "workflow_run_id": workflow_run_id,
                "inputs": json.dumps(plan.input_references),
                "output": json.dumps(output),
                "correlation_id": correlation_id,
                "idempotency_key": plan.idempotency_key,
                "occurred_at": occurred_at,
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

    @staticmethod
    def _organization_wide_roles() -> tuple[Any, ...]:
        from alos.security import Role

        return (Role.DIRECTOR, Role.AI_EXECUTIVE, Role.IT_ADMIN, Role.AUDITOR)

    @staticmethod
    def _upsert_workflow_release(connection: Any, definition: WorkflowDefinition) -> UUID:
        return connection.execute(
            text(
                """
                INSERT INTO workflow.workflow_releases
                    (workflow_id, version, definition, status)
                VALUES (:workflow_id, :version, CAST(:definition AS jsonb), 'STAGED')
                ON CONFLICT (workflow_id, version)
                DO UPDATE SET definition = EXCLUDED.definition
                RETURNING workflow_release_id
                """
            ),
            {
                "workflow_id": definition.workflow_id,
                "version": definition.version,
                "definition": definition.model_dump_json(),
            },
        ).scalar_one()

    @staticmethod
    def _upsert_agent_release(connection: Any, plan: AgentExecutionPlan) -> UUID:
        definition = {
            "agent_id": plan.agent_id,
            "version": plan.agent_version,
            "capability": plan.capability,
            "approved_tools": plan.approved_tools,
        }
        return connection.execute(
            text(
                """
                INSERT INTO agents.agent_releases
                    (agent_id, version, definition, status)
                VALUES (:agent_id, :version, CAST(:definition AS jsonb), 'STAGED')
                ON CONFLICT (agent_id, version)
                DO UPDATE SET definition = agents.agent_releases.definition || EXCLUDED.definition
                RETURNING agent_release_id
                """
            ),
            {
                "agent_id": plan.agent_id,
                "version": plan.agent_version,
                "definition": json.dumps(definition),
            },
        ).scalar_one()

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
    ) -> None:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(CAST(:organization_id AS text)))"),
            {"organization_id": principal.organization_id},
        )
        previous_hash = connection.execute(
            text(
                """
                SELECT entry_hash FROM audit.entries
                WHERE organization_id = :organization_id
                ORDER BY occurred_at DESC, audit_entry_id DESC LIMIT 1
                FOR UPDATE
                """
            ),
            {"organization_id": principal.organization_id},
        ).scalar_one_or_none()
        occurred_at = datetime.now(UTC)
        canonical = json.dumps(
            {
                "organization_id": str(principal.organization_id),
                "actor_id": str(principal.user_id),
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "correlation_id": str(correlation_id),
                "before": before,
                "after": after,
                "occurred_at": occurred_at.isoformat(),
                "previous_hash": previous_hash,
            },
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
        entry_hash = hashlib.sha256(canonical.encode()).hexdigest()
        connection.execute(
            text(
                """
                INSERT INTO audit.entries
                    (organization_id, occurred_at, actor_type, actor_id, active_role,
                     action, entity_type, entity_id, before_masked, after_masked,
                     correlation_id, previous_hash, entry_hash)
                VALUES
                    (:organization_id, :occurred_at, 'HUMAN', :actor_id, :active_role,
                     :action, :entity_type, :entity_id, CAST(:before AS jsonb),
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
                "before": json.dumps(before, default=str) if before is not None else None,
                "after": json.dumps(after, default=str) if after is not None else None,
                "correlation_id": correlation_id,
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
            },
        )
