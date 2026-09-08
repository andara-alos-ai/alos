"""Transactional repositories for scoped operational data, approvals, reports, and search."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from alos.authorization import AccessMode, effective_data_scope, require_business_access
from alos.identity import DataScope, DivisionCode
from alos.operational.models import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalRecord,
    BusinessRecord,
    BusinessRecordRequest,
    EvidenceCreateRequest,
    EvidenceRecord,
    FindingCreateRequest,
    FindingRecord,
    FindingStatusRequest,
    OperationalDashboard,
    Page,
    ProposedActionCreateRequest,
    ProposedActionExecuteRequest,
    ProposedActionRecord,
    ReportDefinitionRecord,
    ReportDefinitionRequest,
    ReportGenerateRequest,
    ReportRecord,
    ReportScheduleRequest,
    SearchResult,
    TaskCreateRequest,
    TaskList,
    TaskRecord,
    TaskStatusRequest,
)
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class OperationalError(RuntimeError):
    """Safe operational-domain failure."""


class OperationalNotFound(OperationalError):
    pass


class OperationalConflict(OperationalError):
    pass


class OperationalRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def list_tasks(
        self,
        actor: ActorContext,
        *,
        status: str | None = None,
        project_id: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TaskList:
        where, parameters = self._task_scope(actor, alias="task")
        if status:
            where.append("task.status = %s")
            parameters.append(status)
        if project_id:
            where.append("task.project_id = %s")
            parameters.append(project_id)
        if search:
            where.append("(task.title ILIKE %s OR task.description ILIKE %s)")
            query = f"%{search.strip()}%"
            parameters.extend((query, query))
        clause = " AND ".join(where)
        with self._connection() as connection:
            total_row = connection.execute(
                f"SELECT count(*) AS total FROM operational.tasks AS task "
                f"JOIN identity.divisions AS division ON division.division_id = task.division_id "
                f"WHERE {clause}",
                parameters,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT task.task_id, task.organization_id, task.workspace_id, task.division_id,
                       division.code AS division_code, task.project_id,
                       project.name AS project_name,
                       task.title, task.description, task.status, task.priority, task.due_date,
                       task.assignee_user_id, task.owner_user_id, task.created_by_user_id,
                       task.created_by_actor_kind, task.evidence_required, task.created_at,
                       task.updated_at, task.completed_at
                FROM operational.tasks AS task
                JOIN identity.divisions AS division ON division.division_id = task.division_id
                LEFT JOIN portfolio.projects AS project ON project.project_id = task.project_id
                WHERE {clause}
                ORDER BY task.due_date ASC NULLS LAST, task.created_at DESC
                LIMIT %s OFFSET %s
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        total = int(total_row["total"] if total_row else 0)
        return TaskList(
            items=[TaskRecord(**row) for row in rows],
            pagination=Page(
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=max(1, ceil(total / page_size)),
            ),
        )

    def get_task(self, actor: ActorContext, task_id: UUID) -> TaskRecord:
        where, parameters = self._task_scope(actor, alias="task")
        where.append("task.task_id = %s")
        parameters.append(task_id)
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT task.task_id, task.organization_id, task.workspace_id, task.division_id,
                       division.code AS division_code, task.project_id,
                       project.name AS project_name,
                       task.title, task.description, task.status, task.priority, task.due_date,
                       task.assignee_user_id, task.owner_user_id, task.created_by_user_id,
                       task.created_by_actor_kind, task.evidence_required, task.created_at,
                       task.updated_at, task.completed_at
                FROM operational.tasks AS task
                JOIN identity.divisions AS division ON division.division_id = task.division_id
                LEFT JOIN portfolio.projects AS project ON project.project_id = task.project_id
                WHERE {' AND '.join(where)}
                """,
                parameters,
            ).fetchone()
        if row is None:
            raise OperationalNotFound("task was not found in the authenticated scope")
        return TaskRecord(**row)

    def create_task(
        self,
        actor: ActorContext,
        request: TaskCreateRequest,
        *,
        correlation_id: UUID,
        actor_kind: str = "HUMAN",
        agent_version_id: UUID | None = None,
        force_draft: bool = False,
    ) -> TaskRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = self._division_id(connection, actor, request.division_code)
            self._validate_project(
                connection,
                actor,
                request.project_id,
                request.workspace_id,
                division_id,
            )
            owner_user_id = request.owner_user_id or actor.user_id
            self._validate_users(
                connection,
                actor.organization_id,
                owner_user_id,
                request.assignee_user_id,
            )
            try:
                row = connection.execute(
                    """
                    INSERT INTO operational.tasks (
                        organization_id, workspace_id, division_id, project_id, title, description,
                        status, priority, due_date, assignee_user_id, owner_user_id,
                        created_by_user_id, created_by_actor_kind, created_by_agent_version_id,
                        evidence_required, idempotency_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (organization_id, idempotency_key) DO UPDATE
                    SET idempotency_key = EXCLUDED.idempotency_key
                    RETURNING task_id
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        division_id,
                        request.project_id,
                        request.title.strip(),
                        request.description.strip(),
                        "DRAFT" if force_draft else request.status,
                        request.priority,
                        request.due_date,
                        request.assignee_user_id,
                        owner_user_id,
                        actor.user_id if actor_kind == "HUMAN" else None,
                        actor_kind,
                        agent_version_id,
                        request.evidence_required,
                        request.idempotency_key,
                    ),
                ).fetchone()
            except UniqueViolation as error:
                raise OperationalConflict(
                    "task idempotency key conflicts with an existing task"
                ) from error
            if row is None:
                raise OperationalError("task could not be created")
            self._audit(
                connection,
                actor,
                action="TASK_DRAFT_CREATED" if force_draft else "TASK_CREATED",
                entity_type="TASK",
                entity_id=row["task_id"],
                correlation_id=correlation_id,
                reason="A scoped actor created a canonical operational task",
                metadata={"division_code": request.division_code.value, "actor_kind": actor_kind},
            )
        return self.get_task(actor, row["task_id"])

    def update_task_status(
        self,
        actor: ActorContext,
        task_id: UUID,
        request: TaskStatusRequest,
        *,
        correlation_id: UUID,
    ) -> TaskRecord:
        task = self.get_task(actor, task_id)
        require_business_access(
            actor,
            access_mode=AccessMode.UPDATE_SCOPED,
            workspace_id=task.workspace_id,
            division_code=task.division_code,
            owner_user_id=task.owner_user_id,
            assignee_user_id=task.assignee_user_id,
        )
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE operational.tasks
                SET status = %s, updated_at = now(),
                    completed_at = CASE WHEN %s = 'DONE' THEN now() ELSE NULL END
                WHERE task_id = %s AND organization_id = %s
                RETURNING task_id
                """,
                (request.status, request.status, task_id, actor.organization_id),
            ).fetchone()
            if row is None:
                raise OperationalNotFound("task was not found")
            self._audit(
                connection,
                actor,
                action="TASK_STATUS_UPDATED",
                entity_type="TASK",
                entity_id=task_id,
                correlation_id=correlation_id,
                reason="A scoped human updated task status",
                metadata={"from": task.status, "to": request.status},
            )
        return self.get_task(actor, task_id)

    def list_evidence(
        self, actor: ActorContext, *, task_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[EvidenceRecord]:
        where, parameters = self._generic_scope(actor, alias="evidence")
        if effective_data_scope(actor) == DataScope.OWN_ASSIGNED:
            where.append("(evidence.owner_user_id = %s OR evidence.uploaded_by_user_id = %s)")
            parameters.extend((actor.user_id, actor.user_id))
        if task_id:
            where.append("evidence.task_id = %s")
            parameters.append(task_id)
        if project_id:
            where.append("evidence.project_id = %s")
            parameters.append(project_id)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT evidence.evidence_id, evidence.workspace_id,
                       division.code AS division_code, evidence.project_id, evidence.task_id,
                       evidence.owner_user_id, evidence.uploaded_by_user_id, evidence.document_id,
                       evidence.object_key, evidence.classification, evidence.validation_status,
                       evidence.version, evidence.metadata, evidence.created_at
                FROM operational.evidence AS evidence
                JOIN identity.divisions AS division ON division.division_id = evidence.division_id
                WHERE {' AND '.join(where)}
                ORDER BY evidence.created_at DESC
                """,
                parameters,
            ).fetchall()
        return [EvidenceRecord(**row) for row in rows]

    def create_evidence(
        self, actor: ActorContext, request: EvidenceCreateRequest, *, correlation_id: UUID
    ) -> EvidenceRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = self._division_id(connection, actor, request.division_code)
            self._validate_project(
                connection, actor, request.project_id, request.workspace_id, division_id
            )
            if request.task_id is not None:
                task = self.get_task(actor, request.task_id)
                if task.workspace_id != request.workspace_id or task.division_id != division_id:
                    raise OperationalConflict("task is outside the evidence scope")
            row = connection.execute(
                """
                INSERT INTO operational.evidence (
                    organization_id, workspace_id, division_id, project_id, task_id,
                    owner_user_id, uploaded_by_user_id, document_id, object_key,
                    classification, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING evidence_id
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    division_id,
                    request.project_id,
                    request.task_id,
                    actor.user_id,
                    actor.user_id,
                    request.document_id,
                    request.object_key,
                    request.classification,
                    Jsonb(request.metadata),
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("evidence could not be registered")
            self._audit(
                connection,
                actor,
                action="EVIDENCE_REGISTERED",
                entity_type="EVIDENCE",
                entity_id=row["evidence_id"],
                correlation_id=correlation_id,
                reason="A scoped human registered evidence metadata",
                metadata={"classification": request.classification},
            )
        records = self.list_evidence(actor, task_id=request.task_id, project_id=request.project_id)
        return next(item for item in records if item.evidence_id == row["evidence_id"])

    def list_findings(
        self, actor: ActorContext, *, status: str | None = None, severity: str | None = None
    ) -> list[FindingRecord]:
        where, parameters = self._generic_scope(actor, alias="finding", division_optional=True)
        if effective_data_scope(actor) == DataScope.OWN_ASSIGNED:
            where.append("(finding.owner_user_id = %s OR finding.created_by_user_id = %s)")
            parameters.extend((actor.user_id, actor.user_id))
        if status:
            where.append("finding.status = %s")
            parameters.append(status)
        if severity:
            where.append("finding.severity = %s")
            parameters.append(severity)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT finding.finding_id, finding.organization_id, finding.workspace_id,
                       finding.division_id, division.code AS division_code, finding.project_id,
                       finding.source_kind, finding.source_id, finding.title, finding.description,
                       finding.severity, finding.status, finding.owner_user_id,
                       finding.recommendation, finding.citation_refs, finding.generated_by,
                       finding.resolution, finding.due_date, finding.created_at, finding.updated_at
                FROM operational.findings AS finding
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = finding.division_id
                WHERE {' AND '.join(where)}
                ORDER BY CASE finding.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                          WHEN 'MEDIUM' THEN 2 ELSE 3 END, finding.created_at DESC
                """,
                parameters,
            ).fetchall()
        return [FindingRecord(**row) for row in rows]

    def create_finding(
        self,
        actor: ActorContext,
        request: FindingCreateRequest,
        *,
        correlation_id: UUID,
        generated_by: str = "HUMAN",
        agent_version_id: UUID | None = None,
    ) -> FindingRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = (
                self._division_id(connection, actor, request.division_code)
                if request.division_code
                else None
            )
            self._validate_project(
                connection, actor, request.project_id, request.workspace_id, division_id
            )
            row = connection.execute(
                """
                INSERT INTO operational.findings (
                    organization_id, workspace_id, division_id, project_id, source_kind,
                    source_id, title, description, severity, owner_user_id, recommendation,
                    citation_refs, generated_by, generated_by_agent_version_id, due_date,
                    created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING finding_id
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    division_id,
                    request.project_id,
                    request.source_kind,
                    request.source_id,
                    request.title.strip(),
                    request.description.strip(),
                    request.severity,
                    request.owner_user_id,
                    request.recommendation.strip(),
                    Jsonb(request.citation_refs),
                    generated_by,
                    agent_version_id,
                    request.due_date,
                    actor.user_id if generated_by == "HUMAN" else None,
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("finding could not be created")
            self._audit(
                connection,
                actor,
                action="FINDING_CREATED",
                entity_type="FINDING",
                entity_id=row["finding_id"],
                correlation_id=correlation_id,
                reason="A governed evidence-backed finding was created",
                metadata={"severity": request.severity, "generated_by": generated_by},
            )
        return next(
            item
            for item in self.list_findings(actor)
            if item.finding_id == row["finding_id"]
        )

    def update_finding_status(
        self,
        actor: ActorContext,
        finding_id: UUID,
        request: FindingStatusRequest,
        *,
        correlation_id: UUID,
    ) -> FindingRecord:
        current = next(
            (item for item in self.list_findings(actor) if item.finding_id == finding_id), None
        )
        if current is None:
            raise OperationalNotFound("finding was not found in the authenticated scope")
        require_business_access(
            actor,
            access_mode=AccessMode.UPDATE_SCOPED,
            workspace_id=current.workspace_id,
            division_code=current.division_code,
            owner_user_id=current.owner_user_id,
        )
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE operational.findings
                SET status = %s, resolution = %s, updated_at = now()
                WHERE finding_id = %s AND organization_id = %s
                """,
                (request.status, request.resolution, finding_id, actor.organization_id),
            )
            self._audit(
                connection,
                actor,
                action="FINDING_STATUS_UPDATED",
                entity_type="FINDING",
                entity_id=finding_id,
                correlation_id=correlation_id,
                reason="A scoped human updated finding status",
                metadata={"from": current.status, "to": request.status},
            )
        return next(item for item in self.list_findings(actor) if item.finding_id == finding_id)

    def list_proposed_actions(self, actor: ActorContext) -> list[ProposedActionRecord]:
        where, parameters = self._generic_scope(
            actor, alias="action", division_optional=True
        )
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT action.proposed_action_id, action.organization_id,
                       action.workspace_id, action.division_id,
                       division.code AS division_code, action.project_id,
                       action.action_type, action.payload, action.payload_digest,
                       action.risk_level, action.status, action.requested_by_user_id,
                       action.requested_by_agent_version_id, action.created_at,
                       action.executed_at, action.idempotency_key,
                       approval.approval_request_id, approval.status AS approval_status,
                       action.executed_entity_type, action.executed_entity_id
                FROM operational.proposed_actions AS action
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = action.division_id
                LEFT JOIN operational.approval_requests AS approval
                  ON approval.subject_id = action.proposed_action_id
                 AND approval.approval_kind = 'PROPOSED_ACTION'
                 AND approval.status <> 'CANCELLED'
                WHERE {' AND '.join(where)}
                ORDER BY action.created_at DESC
                """,
                parameters,
            ).fetchall()
        return [ProposedActionRecord(**row) for row in rows]

    def create_proposed_action(
        self,
        actor: ActorContext,
        request: ProposedActionCreateRequest,
        *,
        correlation_id: UUID,
        agent_version_id: UUID | None = None,
    ) -> ProposedActionRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.REQUEST_APPROVAL,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        payload = self._validated_action_payload(request)
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT proposed_action_id FROM operational.proposed_actions
                WHERE organization_id = %s AND idempotency_key = %s
                """,
                (actor.organization_id, request.idempotency_key),
            ).fetchone()
            if existing is not None:
                action_id = existing["proposed_action_id"]
            else:
                division_id = (
                    self._division_id(connection, actor, request.division_code)
                    if request.division_code
                    else None
                )
                self._validate_project(
                    connection,
                    actor,
                    request.project_id,
                    request.workspace_id,
                    division_id,
                )
                row = connection.execute(
                    """
                    INSERT INTO operational.proposed_actions (
                        organization_id, workspace_id, division_id, project_id,
                        action_type, payload, payload_digest, risk_level, status,
                        requested_by_user_id, requested_by_agent_version_id,
                        idempotency_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              'APPROVAL_REQUIRED', %s, %s, %s)
                    RETURNING proposed_action_id
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        division_id,
                        request.project_id,
                        request.action_type,
                        Jsonb(payload),
                        digest,
                        request.risk_level,
                        actor.user_id if agent_version_id is None else None,
                        agent_version_id,
                        request.idempotency_key,
                    ),
                ).fetchone()
                if row is None:
                    raise OperationalError("proposed action could not be created")
                action_id = row["proposed_action_id"]
                approval = connection.execute(
                    """
                    INSERT INTO operational.approval_requests (
                        organization_id, workspace_id, division_id, project_id,
                        approval_kind, subject_type, subject_id, payload_digest,
                        title, description, urgency, requested_by_user_id,
                        requested_by_agent_version_id
                    ) VALUES (%s, %s, %s, %s, 'PROPOSED_ACTION', %s, %s, %s,
                              %s, %s, %s, %s, %s)
                    RETURNING approval_request_id
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        division_id,
                        request.project_id,
                        request.action_type,
                        action_id,
                        digest,
                        request.title.strip(),
                        request.description.strip(),
                        request.urgency,
                        actor.user_id if agent_version_id is None else None,
                        agent_version_id,
                    ),
                ).fetchone()
                if approval is None:
                    raise OperationalError("proposed action approval could not be created")
                self._audit(
                    connection,
                    actor,
                    action="PROPOSED_ACTION_CREATED",
                    entity_type="PROPOSED_ACTION",
                    entity_id=action_id,
                    correlation_id=correlation_id,
                    reason="A material action was preserved as an immutable approval-bound payload",
                    metadata={"action_type": request.action_type, "payload_digest": digest},
                )
        return self._proposed_action(actor, action_id)

    def execute_proposed_action(
        self,
        actor: ActorContext,
        proposed_action_id: UUID,
        request: ProposedActionExecuteRequest,
        *,
        correlation_id: UUID,
    ) -> ProposedActionRecord:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT action.*, division.code AS division_code,
                       approval.status AS approval_status,
                       approval.payload_digest AS approval_payload_digest,
                       approval.approval_token_digest
                FROM operational.proposed_actions AS action
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = action.division_id
                JOIN operational.approval_requests AS approval
                  ON approval.subject_id = action.proposed_action_id
                 AND approval.approval_kind = 'PROPOSED_ACTION'
                WHERE action.proposed_action_id = %s
                  AND action.organization_id = %s
                  AND action.workspace_id = ANY(%s)
                FOR UPDATE OF action
                """,
                (proposed_action_id, actor.organization_id, actor.workspace_ids),
            ).fetchone()
            if row is None:
                raise OperationalNotFound("proposed action was not found")
            require_business_access(
                actor,
                access_mode=AccessMode.EXECUTE_APPROVED_ACTION,
                workspace_id=row["workspace_id"],
                division_code=row["division_code"],
            )
            expected_digest = request.payload_digest.lower()
            if (
                row["status"] != "APPROVED"
                or row["approval_status"] != "APPROVED"
                or row["approval_token_digest"] is None
                or row["payload_digest"] != expected_digest
                or row["approval_payload_digest"] != expected_digest
            ):
                raise OperationalConflict(
                    "proposed action requires a matching unmodified approval"
                )
            entity_type, entity_id = self._execute_action_payload(connection, actor, row)
            updated = connection.execute(
                """
                UPDATE operational.proposed_actions
                SET status = 'EXECUTED', executed_at = now(),
                    executed_entity_type = %s, executed_entity_id = %s
                WHERE proposed_action_id = %s AND status = 'APPROVED'
                RETURNING proposed_action_id
                """,
                (entity_type, entity_id, proposed_action_id),
            ).fetchone()
            if updated is None:
                raise OperationalConflict("proposed action was already executed")
            self._audit(
                connection,
                actor,
                action="PROPOSED_ACTION_EXECUTED",
                entity_type="PROPOSED_ACTION",
                entity_id=proposed_action_id,
                correlation_id=correlation_id,
                reason="An independently approved digest-bound action executed exactly once",
                metadata={
                    "payload_digest": expected_digest,
                    "executed_entity_type": entity_type,
                    "executed_entity_id": str(entity_id),
                },
            )
        return self._proposed_action(actor, proposed_action_id)

    def _proposed_action(
        self, actor: ActorContext, proposed_action_id: UUID
    ) -> ProposedActionRecord:
        action = next(
            (
                item
                for item in self.list_proposed_actions(actor)
                if item.proposed_action_id == proposed_action_id
            ),
            None,
        )
        if action is None:
            raise OperationalNotFound("proposed action was not found")
        return action

    @staticmethod
    def _validated_action_payload(request: ProposedActionCreateRequest) -> dict[str, Any]:
        if request.action_type == "TASK_CREATE":
            parsed = TaskCreateRequest.model_validate(request.payload)
            if (
                parsed.workspace_id != request.workspace_id
                or parsed.division_code != request.division_code
                or parsed.project_id != request.project_id
            ):
                raise OperationalConflict("task payload scope does not match action scope")
            return parsed.model_dump(mode="json")
        parsed_finding = FindingCreateRequest.model_validate(request.payload)
        if (
            parsed_finding.workspace_id != request.workspace_id
            or parsed_finding.division_code != request.division_code
            or parsed_finding.project_id != request.project_id
        ):
            raise OperationalConflict("finding payload scope does not match action scope")
        return parsed_finding.model_dump(mode="json")

    def _execute_action_payload(
        self,
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        action: dict[str, Any],
    ) -> tuple[str, UUID]:
        if action["action_type"] == "TASK_CREATE":
            task_request = TaskCreateRequest.model_validate(action["payload"])
            division_id = self._division_id(
                connection, actor, task_request.division_code
            )
            self._validate_project(
                connection,
                actor,
                task_request.project_id,
                task_request.workspace_id,
                division_id,
            )
            owner_user_id = task_request.owner_user_id or actor.user_id
            self._validate_users(
                connection,
                actor.organization_id,
                owner_user_id,
                task_request.assignee_user_id,
            )
            row = connection.execute(
                """
                INSERT INTO operational.tasks (
                    organization_id, workspace_id, division_id, project_id, title,
                    description, status, priority, due_date, assignee_user_id,
                    owner_user_id, created_by_user_id, created_by_actor_kind,
                    evidence_required, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          'HUMAN', %s, %s)
                RETURNING task_id
                """,
                (
                    actor.organization_id,
                    task_request.workspace_id,
                    division_id,
                    task_request.project_id,
                    task_request.title.strip(),
                    task_request.description.strip(),
                    task_request.status,
                    task_request.priority,
                    task_request.due_date,
                    task_request.assignee_user_id,
                    owner_user_id,
                    actor.user_id,
                    task_request.evidence_required,
                    f"approved-action:{action['proposed_action_id']}",
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("approved task action could not execute")
            return "TASK", row["task_id"]

        finding_request = FindingCreateRequest.model_validate(action["payload"])
        finding_division_id = (
            self._division_id(connection, actor, finding_request.division_code)
            if finding_request.division_code
            else None
        )
        self._validate_project(
            connection,
            actor,
            finding_request.project_id,
            finding_request.workspace_id,
            finding_division_id,
        )
        row = connection.execute(
            """
            INSERT INTO operational.findings (
                organization_id, workspace_id, division_id, project_id, source_kind,
                source_id, title, description, severity, owner_user_id,
                recommendation, citation_refs, generated_by, due_date,
                created_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      'HUMAN', %s, %s)
            RETURNING finding_id
            """,
            (
                actor.organization_id,
                finding_request.workspace_id,
                finding_division_id,
                finding_request.project_id,
                finding_request.source_kind,
                finding_request.source_id,
                finding_request.title.strip(),
                finding_request.description.strip(),
                finding_request.severity,
                finding_request.owner_user_id,
                finding_request.recommendation.strip(),
                Jsonb(finding_request.citation_refs),
                finding_request.due_date,
                actor.user_id,
            ),
        ).fetchone()
        if row is None:
            raise OperationalError("approved finding action could not execute")
        return "FINDING", row["finding_id"]

    def list_approvals(
        self, actor: ActorContext, *, status: str | None = None
    ) -> list[ApprovalRecord]:
        where, parameters = self._generic_scope(actor, alias="approval", division_optional=True)
        if status:
            where.append("approval.status = %s")
            parameters.append(status)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT approval.approval_request_id, approval.organization_id,
                       approval.workspace_id, approval.division_id,
                       division.code AS division_code, approval.project_id,
                       approval.approval_kind, approval.subject_type, approval.subject_id,
                       approval.payload_digest, approval.title, approval.description,
                       approval.urgency, approval.status, approval.requested_by_user_id,
                       approval.approver_user_id, approval.decision_notes,
                       approval.requested_at, approval.decided_at
                FROM operational.approval_requests AS approval
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = approval.division_id
                WHERE {' AND '.join(where)}
                ORDER BY CASE approval.urgency WHEN 'URGENT' THEN 0 ELSE 1 END,
                         approval.requested_at ASC
                """,
                parameters,
            ).fetchall()
        return [ApprovalRecord(**row) for row in rows]

    def create_approval(
        self,
        actor: ActorContext,
        request: ApprovalCreateRequest,
        *,
        correlation_id: UUID,
        agent_version_id: UUID | None = None,
    ) -> ApprovalRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.REQUEST_APPROVAL,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = (
                self._division_id(connection, actor, request.division_code)
                if request.division_code
                else None
            )
            row = connection.execute(
                """
                INSERT INTO operational.approval_requests (
                    organization_id, workspace_id, division_id, project_id, approval_kind,
                    subject_type, subject_id, payload_digest, title, description, urgency,
                    requested_by_user_id, requested_by_agent_version_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, lower(%s), %s, %s, %s, %s, %s)
                RETURNING approval_request_id
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    division_id,
                    request.project_id,
                    request.approval_kind,
                    request.subject_type,
                    request.subject_id,
                    request.payload_digest,
                    request.title.strip(),
                    request.description.strip(),
                    request.urgency,
                    actor.user_id if agent_version_id is None else None,
                    agent_version_id,
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("approval request could not be created")
            self._audit(
                connection,
                actor,
                action="APPROVAL_REQUESTED",
                entity_type="APPROVAL_REQUEST",
                entity_id=row["approval_request_id"],
                correlation_id=correlation_id,
                reason="A material action was bound to an immutable payload digest",
                metadata={
                    "kind": request.approval_kind,
                    "payload_digest": request.payload_digest.lower(),
                },
            )
        return next(
            item
            for item in self.list_approvals(actor)
            if item.approval_request_id == row["approval_request_id"]
        )

    def decide_approval(
        self,
        actor: ActorContext,
        approval_request_id: UUID,
        request: ApprovalDecisionRequest,
        *,
        correlation_id: UUID,
    ) -> ApprovalRecord:
        current = next(
            (
                item
                for item in self.list_approvals(actor, status="PENDING")
                if item.approval_request_id == approval_request_id
            ),
            None,
        )
        if current is None:
            raise OperationalNotFound("pending approval was not found in the authenticated scope")
        require_business_access(
            actor,
            access_mode=AccessMode.EXECUTE_APPROVED_ACTION,
            workspace_id=current.workspace_id,
            division_code=current.division_code,
        )
        if current.requested_by_user_id == actor.user_id:
            raise OperationalConflict("requester cannot approve their own request")
        if current.payload_digest != request.payload_digest.lower():
            raise OperationalConflict("approval payload digest no longer matches")
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE operational.approval_requests
                SET status = %s, approver_user_id = %s, decision_notes = %s,
                    decided_at = now(), approval_token_digest = encode(
                        digest(payload_digest || ':' || %s::text || ':' || %s, 'sha256'), 'hex'
                    )
                WHERE approval_request_id = %s AND organization_id = %s AND status = 'PENDING'
                  AND payload_digest = %s
                RETURNING approval_request_id
                """,
                (
                    request.decision,
                    actor.user_id,
                    request.notes.strip(),
                    actor.user_id,
                    request.decision,
                    approval_request_id,
                    actor.organization_id,
                    request.payload_digest.lower(),
                ),
            ).fetchone()
            if row is None:
                raise OperationalConflict("approval was already decided or its payload changed")
            if current.approval_kind == "PROPOSED_ACTION":
                action_status = (
                    "APPROVED" if request.decision == "APPROVED" else "REJECTED"
                )
                action = connection.execute(
                    """
                    UPDATE operational.proposed_actions SET status = %s
                    WHERE proposed_action_id = %s AND organization_id = %s
                      AND status = 'APPROVAL_REQUIRED' AND payload_digest = %s
                    RETURNING proposed_action_id
                    """,
                    (
                        action_status,
                        current.subject_id,
                        actor.organization_id,
                        request.payload_digest.lower(),
                    ),
                ).fetchone()
                if action is None:
                    raise OperationalConflict(
                        "proposed action changed or is no longer awaiting approval"
                    )
            self._audit(
                connection,
                actor,
                action="APPROVAL_DECIDED",
                entity_type="APPROVAL_REQUEST",
                entity_id=approval_request_id,
                correlation_id=correlation_id,
                reason="An independent human recorded a digest-bound decision",
                metadata={
                    "decision": request.decision,
                    "payload_digest": request.payload_digest.lower(),
                },
            )
        return next(
            item
            for item in self.list_approvals(actor)
            if item.approval_request_id == approval_request_id
        )

    def list_report_definitions(self, actor: ActorContext) -> list[ReportDefinitionRecord]:
        where, parameters = self._generic_scope(actor, alias="definition", division_optional=True)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT definition.report_definition_id, definition.workspace_id,
                       definition.division_id, division.code AS division_code,
                       definition.project_id, definition.name, definition.template_key,
                       definition.scope, definition.period, definition.sections,
                       definition.data_sources, definition.status, definition.review_required,
                       definition.recipient_user_ids, definition.owner_user_id,
                       definition.created_at, definition.updated_at, schedule.schedule_expression,
                       schedule.timezone, schedule.next_run_at
                FROM reporting.definitions AS definition
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = definition.division_id
                LEFT JOIN reporting.schedules AS schedule
                  ON schedule.report_definition_id = definition.report_definition_id
                WHERE {' AND '.join(where)}
                ORDER BY definition.updated_at DESC
                """,
                parameters,
            ).fetchall()
        return [ReportDefinitionRecord(**row) for row in rows]

    def create_report_definition(
        self, actor: ActorContext, request: ReportDefinitionRequest, *, correlation_id: UUID
    ) -> ReportDefinitionRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        if request.scope == "COMPANY" and effective_data_scope(actor) != DataScope.COMPANY:
            raise OperationalConflict("company report scope requires Director authority")
        with self._transaction() as connection:
            division_id = (
                self._division_id(connection, actor, request.division_code)
                if request.division_code
                else None
            )
            row = connection.execute(
                """
                INSERT INTO reporting.definitions (
                    organization_id, workspace_id, division_id, project_id, name, template_key,
                    scope, period, sections, data_sources, review_required, recipient_user_ids,
                    owner_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_definition_id
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    division_id,
                    request.project_id,
                    request.name.strip(),
                    request.template_key,
                    request.scope,
                    request.period,
                    Jsonb(request.sections),
                    Jsonb(request.data_sources),
                    request.review_required,
                    request.recipient_user_ids,
                    actor.user_id,
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("report definition could not be created")
            self._audit(
                connection,
                actor,
                action="REPORT_DEFINITION_DRAFTED",
                entity_type="REPORT_DEFINITION",
                entity_id=row["report_definition_id"],
                correlation_id=correlation_id,
                reason="A scoped report definition draft was created for human review",
                metadata={"scope": request.scope, "period": request.period},
            )
        return next(
            item
            for item in self.list_report_definitions(actor)
            if item.report_definition_id == row["report_definition_id"]
        )

    def configure_report_schedule(
        self,
        actor: ActorContext,
        report_definition_id: UUID,
        request: ReportScheduleRequest,
        *,
        correlation_id: UUID,
    ) -> ReportDefinitionRecord:
        from alos.jobs.repository import next_schedule_at

        calculated_next_run = next_schedule_at(
            request.schedule_expression, datetime.now(UTC), request.timezone
        )
        definition = next(
            (
                item
                for item in self.list_report_definitions(actor)
                if item.report_definition_id == report_definition_id
            ),
            None,
        )
        if definition is None:
            raise OperationalNotFound("report definition was not found")
        require_business_access(
            actor,
            access_mode=AccessMode.REQUEST_APPROVAL,
            workspace_id=definition.workspace_id,
            division_code=definition.division_code,
        )
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO reporting.schedules (
                    report_definition_id, timezone, schedule_expression, next_run_at,
                    active, confirmed_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_definition_id) DO UPDATE
                SET timezone = EXCLUDED.timezone,
                    schedule_expression = EXCLUDED.schedule_expression,
                    next_run_at = EXCLUDED.next_run_at,
                    active = EXCLUDED.active,
                    confirmed_by_user_id = EXCLUDED.confirmed_by_user_id
                """,
                (
                    report_definition_id,
                    request.timezone,
                    request.schedule_expression,
                    calculated_next_run,
                    request.confirm,
                    actor.user_id if request.confirm else None,
                ),
            )
            if request.confirm:
                connection.execute(
                    "UPDATE reporting.definitions SET status = 'ACTIVE', updated_at = now() "
                    "WHERE report_definition_id = %s",
                    (report_definition_id,),
                )
            self._audit(
                connection,
                actor,
                action=(
                    "REPORT_SCHEDULE_CONFIRMED"
                    if request.confirm
                    else "REPORT_SCHEDULE_DRAFTED"
                ),
                entity_type="REPORT_DEFINITION",
                entity_id=report_definition_id,
                correlation_id=correlation_id,
                reason="A durable PostgreSQL-backed report schedule was configured",
                metadata={"active": request.confirm, "timezone": request.timezone},
            )
        return next(
            item
            for item in self.list_report_definitions(actor)
            if item.report_definition_id == report_definition_id
        )

    def list_reports(self, actor: ActorContext) -> list[ReportRecord]:
        if not actor.workspace_ids:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT report.report_id, report.report_definition_id, report.organization_id,
                       report.workspace_id, report.status, report.content, report.provenance,
                       report.idempotency_key, report.created_at, report.updated_at
                FROM reporting.reports AS report
                WHERE report.organization_id = %s AND report.workspace_id = ANY(%s)
                ORDER BY report.created_at DESC
                """,
                (actor.organization_id, actor.workspace_ids),
            ).fetchall()
        return [ReportRecord(**row) for row in rows]

    def generate_report(
        self,
        actor: ActorContext,
        report_definition_id: UUID,
        request: ReportGenerateRequest,
        *,
        correlation_id: UUID,
    ) -> ReportRecord:
        definition = next(
            (
                item
                for item in self.list_report_definitions(actor)
                if item.report_definition_id == report_definition_id
            ),
            None,
        )
        if definition is None:
            raise OperationalNotFound("report definition was not found")
        with self._transaction() as connection:
            metrics = connection.execute(
                """
                WITH report_scope AS (
                    SELECT %s::uuid AS organization_id, %s::uuid AS workspace_id,
                           %s::uuid AS division_id, %s::uuid AS project_id,
                           %s::uuid AS actor_user_id, %s::boolean AS own_only
                )
                SELECT
                    (SELECT count(*) FROM portfolio.projects AS project, report_scope
                     WHERE project.organization_id = report_scope.organization_id
                       AND project.workspace_id = report_scope.workspace_id
                       AND (report_scope.division_id IS NULL
                            OR project.division_id = report_scope.division_id)
                       AND (report_scope.project_id IS NULL
                            OR project.project_id = report_scope.project_id)
                       AND (NOT report_scope.own_only
                            OR project.owner_user_id = report_scope.actor_user_id)) AS projects,
                    (SELECT count(*) FROM operational.tasks AS task, report_scope
                     WHERE task.organization_id = report_scope.organization_id
                       AND task.workspace_id = report_scope.workspace_id
                       AND (report_scope.division_id IS NULL
                            OR task.division_id = report_scope.division_id)
                       AND (report_scope.project_id IS NULL
                            OR task.project_id = report_scope.project_id)
                       AND (NOT report_scope.own_only
                            OR task.owner_user_id = report_scope.actor_user_id
                            OR task.assignee_user_id = report_scope.actor_user_id)) AS tasks,
                    (SELECT count(*) FROM operational.tasks AS task, report_scope
                     WHERE task.organization_id = report_scope.organization_id
                       AND task.workspace_id = report_scope.workspace_id
                       AND (report_scope.division_id IS NULL
                            OR task.division_id = report_scope.division_id)
                       AND (report_scope.project_id IS NULL
                            OR task.project_id = report_scope.project_id)
                       AND (NOT report_scope.own_only
                            OR task.owner_user_id = report_scope.actor_user_id
                            OR task.assignee_user_id = report_scope.actor_user_id)
                       AND task.status NOT IN ('DONE', 'CANCELLED')
                       AND task.due_date < current_date) AS overdue_tasks,
                    (SELECT count(*) FROM operational.findings AS finding, report_scope
                     WHERE finding.organization_id = report_scope.organization_id
                       AND finding.workspace_id = report_scope.workspace_id
                       AND (report_scope.division_id IS NULL
                            OR finding.division_id = report_scope.division_id)
                       AND (report_scope.project_id IS NULL
                            OR finding.project_id = report_scope.project_id)
                       AND (NOT report_scope.own_only
                            OR finding.owner_user_id = report_scope.actor_user_id)
                       AND finding.status <> 'RESOLVED') AS open_findings,
                    (SELECT count(*) FROM operational.approval_requests AS approval, report_scope
                     WHERE approval.organization_id = report_scope.organization_id
                       AND approval.workspace_id = report_scope.workspace_id
                       AND (report_scope.division_id IS NULL
                            OR approval.division_id = report_scope.division_id)
                       AND (report_scope.project_id IS NULL
                            OR approval.project_id = report_scope.project_id)
                       AND (NOT report_scope.own_only
                            OR approval.requested_by_user_id = report_scope.actor_user_id)
                       AND approval.status = 'PENDING') AS pending_approvals
                """,
                (
                    actor.organization_id,
                    definition.workspace_id,
                    definition.division_id,
                    definition.project_id,
                    actor.user_id,
                    definition.scope == "OWN_ASSIGNED",
                ),
            ).fetchone()
            content = {
                "title": definition.name,
                "generated_at": datetime.now(UTC).isoformat(),
                "scope": definition.scope,
                "metrics": dict(metrics or {}),
                "sections": definition.sections,
            }
            provenance = [
                {"source": "portfolio.projects", "kind": "INTERNAL_SOURCE"},
                {"source": "operational.tasks", "kind": "INTERNAL_SOURCE"},
                {"source": "operational.findings", "kind": "INTERNAL_SOURCE"},
                {"source": "operational.approval_requests", "kind": "INTERNAL_SOURCE"},
            ]
            status = "DRAFT" if definition.review_required else "READY"
            row = connection.execute(
                """
                INSERT INTO reporting.reports (
                    report_definition_id, organization_id, workspace_id, status, content,
                    provenance, idempotency_key, requested_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_definition_id, idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING report_id
                """,
                (
                    report_definition_id,
                    actor.organization_id,
                    definition.workspace_id,
                    status,
                    Jsonb(content),
                    Jsonb(provenance),
                    request.idempotency_key,
                    actor.user_id,
                ),
            ).fetchone()
            if row is None:
                raise OperationalError("report could not be generated")
            self._audit(
                connection,
                actor,
                action="REPORT_GENERATED",
                entity_type="REPORT",
                entity_id=row["report_id"],
                correlation_id=correlation_id,
                reason="A report draft was generated from canonical ALOS data",
                metadata={"status": status, "definition_id": str(report_definition_id)},
            )
        return next(item for item in self.list_reports(actor) if item.report_id == row["report_id"])

    def list_business_records(
        self, actor: ActorContext, division_code: DivisionCode, *, record_type: str | None = None
    ) -> list[BusinessRecord]:
        require_business_access(actor, access_mode=AccessMode.READ, division_code=division_code)
        where, parameters = self._generic_scope(actor, alias="record")
        where.append("record.domain = %s")
        parameters.append(division_code.value)
        if record_type:
            where.append("record.record_type = %s")
            parameters.append(record_type)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT record.business_record_id, record.workspace_id,
                       division.code AS division_code, record.project_id, record.domain,
                       record.record_type, record.record_key, record.title, record.status,
                       record.classification, record.payload, record.effective_date,
                       record.expires_at, record.owner_user_id, record.created_at, record.updated_at
                FROM business.records AS record
                JOIN identity.divisions AS division ON division.division_id = record.division_id
                WHERE {' AND '.join(where)}
                ORDER BY record.updated_at DESC
                """,
                parameters,
            ).fetchall()
        return [BusinessRecord(**row) for row in rows]

    def create_business_record(
        self,
        actor: ActorContext,
        division_code: DivisionCode,
        request: BusinessRecordRequest,
        *,
        correlation_id: UUID,
    ) -> BusinessRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=division_code,
        )
        with self._transaction() as connection:
            division_id = self._division_id(connection, actor, division_code)
            try:
                row = connection.execute(
                    """
                    INSERT INTO business.records (
                        organization_id, workspace_id, division_id, project_id, domain,
                        record_type, record_key, title, classification, payload,
                        effective_date, expires_at, owner_user_id, created_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING business_record_id
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        division_id,
                        request.project_id,
                        division_code.value,
                        request.record_type,
                        request.record_key,
                        request.title.strip(),
                        request.classification,
                        Jsonb(request.payload),
                        request.effective_date,
                        request.expires_at,
                        actor.user_id,
                        actor.user_id,
                    ),
                ).fetchone()
            except (UniqueViolation, psycopg.errors.CheckViolation) as error:
                raise OperationalConflict(
                    "record key or division record type is invalid"
                ) from error
            if row is None:
                raise OperationalError("business record could not be created")
            self._audit(
                connection,
                actor,
                action="BUSINESS_RECORD_DRAFTED",
                entity_type="BUSINESS_RECORD",
                entity_id=row["business_record_id"],
                correlation_id=correlation_id,
                reason="A scoped division record draft was created",
                metadata={"domain": division_code.value, "record_type": request.record_type},
            )
        return next(
            item
            for item in self.list_business_records(actor, division_code)
            if item.business_record_id == row["business_record_id"]
        )

    def global_search(
        self, actor: ActorContext, query: str, *, limit: int = 20
    ) -> list[SearchResult]:
        term = f"%{query.strip()}%"
        workspace_ids = actor.workspace_ids
        if not workspace_ids:
            return []
        division_codes = [code.value for code in actor.division_codes]
        company_scope = effective_data_scope(actor) == DataScope.COMPANY
        results: list[SearchResult] = []
        with self._connection() as connection:
            division_rows = connection.execute(
                """
                SELECT division.division_id AS entity_id, division.name AS title,
                       division.code AS division_code, division.created_at AS updated_at
                FROM identity.divisions AS division
                WHERE division.organization_id = %s
                  AND (division.name ILIKE %s OR division.code ILIKE %s)
                  AND (%s OR division.code = ANY(%s))
                ORDER BY division.name LIMIT %s
                """,
                (actor.organization_id, term, term, company_scope, division_codes, limit),
            ).fetchall()
            results.extend(
                SearchResult(
                    entity_type="DIVISION",
                    entity_id=row["entity_id"],
                    title=row["title"],
                    subtitle=row["division_code"],
                    href=f"/divisions?division={row['division_code']}",
                    division_code=row["division_code"],
                    updated_at=row["updated_at"],
                )
                for row in division_rows
            )
            queries = (
                (
                    "PROJECT",
                    """
                    SELECT project.project_id AS entity_id, project.name AS title,
                           project.status AS subtitle, division.code AS division_code,
                           project.updated_at
                    FROM portfolio.projects AS project
                    JOIN identity.divisions AS division
                      ON division.division_id = project.division_id
                    WHERE project.organization_id = %s AND project.workspace_id = ANY(%s)
                      AND (project.name ILIKE %s OR project.code ILIKE %s)
                      AND (%s OR division.code = ANY(%s))
                    ORDER BY project.updated_at DESC LIMIT %s
                    """,
                    "/projects",
                ),
                (
                    "TASK",
                    """
                    SELECT task.task_id AS entity_id, task.title, task.status AS subtitle,
                           division.code AS division_code, task.updated_at
                    FROM operational.tasks AS task
                    JOIN identity.divisions AS division ON division.division_id = task.division_id
                    WHERE task.organization_id = %s AND task.workspace_id = ANY(%s)
                      AND (task.title ILIKE %s OR task.description ILIKE %s)
                      AND (%s OR division.code = ANY(%s))
                    ORDER BY task.updated_at DESC LIMIT %s
                    """,
                    "/tasks",
                ),
                (
                    "DOCUMENT",
                    """
                    SELECT document.document_id AS entity_id, document.title,
                           document.status AS subtitle, division.code AS division_code,
                           document.updated_at
                    FROM documents.records AS document
                    LEFT JOIN identity.divisions AS division
                      ON division.division_id = document.division_id
                    WHERE document.organization_id = %s AND document.workspace_id = ANY(%s)
                      AND (document.title ILIKE %s OR document.category ILIKE %s)
                      AND (%s OR division.code IS NULL OR division.code = ANY(%s))
                    ORDER BY document.updated_at DESC LIMIT %s
                    """,
                    "/documents",
                ),
                (
                    "FINDING",
                    """
                    SELECT finding.finding_id AS entity_id, finding.title,
                           finding.severity || ' · ' || finding.status AS subtitle,
                           division.code AS division_code, finding.updated_at
                    FROM operational.findings AS finding
                    LEFT JOIN identity.divisions AS division
                      ON division.division_id = finding.division_id
                    WHERE finding.organization_id = %s AND finding.workspace_id = ANY(%s)
                      AND (finding.title ILIKE %s OR finding.description ILIKE %s)
                      AND (%s OR division.code IS NULL OR division.code = ANY(%s))
                    ORDER BY finding.updated_at DESC LIMIT %s
                    """,
                    "/findings",
                ),
            )
            for entity_type, statement, href in queries:
                rows = connection.execute(
                    statement,
                    (
                        actor.organization_id,
                        workspace_ids,
                        term,
                        term,
                        company_scope,
                        division_codes,
                        limit,
                    ),
                ).fetchall()
                results.extend(
                    SearchResult(
                        entity_type=entity_type,
                        entity_id=row["entity_id"],
                        title=row["title"],
                        subtitle=row["subtitle"],
                        href=f"{href}?id={row['entity_id']}",
                        division_code=row["division_code"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                )
        return sorted(results, key=lambda item: item.updated_at, reverse=True)[:limit]

    def dashboard(self, actor: ActorContext) -> OperationalDashboard:
        tasks = self.list_tasks(actor, page_size=8).items
        findings = self.list_findings(actor)[:8]
        approvals = self.list_approvals(actor)[:8]
        reports = self.list_reports(actor)[:8]
        return OperationalDashboard(
            generated_at=datetime.now(UTC),
            scope=effective_data_scope(actor).value,
            metrics={
                "tasks": self.list_tasks(actor, page_size=1).pagination.total_items,
                "overdue_tasks": sum(
                    1
                    for task in self.list_tasks(actor, page_size=100).items
                    if task.due_date
                    and task.due_date < datetime.now(UTC).date()
                    and task.status not in {"DONE", "CANCELLED"}
                ),
                "open_findings": sum(1 for item in findings if item.status != "RESOLVED"),
                "pending_approvals": sum(1 for item in approvals if item.status == "PENDING"),
                "reports": len(reports),
            },
            tasks=tasks,
            findings=findings,
            approvals=approvals,
            reports=reports,
        )

    def _task_scope(self, actor: ActorContext, *, alias: str) -> tuple[list[str], list[Any]]:
        where, parameters = self._generic_scope(actor, alias=alias)
        if effective_data_scope(actor) == DataScope.OWN_ASSIGNED:
            where.append(f"({alias}.owner_user_id = %s OR {alias}.assignee_user_id = %s)")
            parameters.extend((actor.user_id, actor.user_id))
        return where, parameters

    @staticmethod
    def _generic_scope(
        actor: ActorContext, *, alias: str, division_optional: bool = False
    ) -> tuple[list[str], list[Any]]:
        if not actor.workspace_ids:
            return ["false"], []
        where = [f"{alias}.organization_id = %s", f"{alias}.workspace_id = ANY(%s)"]
        parameters: list[Any] = [actor.organization_id, actor.workspace_ids]
        if effective_data_scope(actor) != DataScope.COMPANY:
            if not actor.division_codes:
                return [*where, "false"], parameters
            optional = f"{alias}.division_id IS NULL OR " if division_optional else ""
            where.append(
                f"({optional}{alias}.division_id IN ("
                "SELECT division_id FROM identity.divisions "
                "WHERE organization_id = %s AND code = ANY(%s)))"
            )
            parameters.extend(
                (actor.organization_id, [code.value for code in actor.division_codes])
            )
        return where, parameters

    @staticmethod
    def _division_id(
        connection: psycopg.Connection[Any], actor: ActorContext, division_code: DivisionCode
    ) -> UUID:
        row = connection.execute(
            "SELECT division_id FROM identity.divisions WHERE organization_id = %s AND code = %s",
            (actor.organization_id, division_code.value),
        ).fetchone()
        if row is None:
            raise OperationalNotFound("division was not found")
        return UUID(str(row["division_id"]))

    @staticmethod
    def _validate_project(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        project_id: UUID | None,
        workspace_id: UUID,
        division_id: UUID | None,
    ) -> None:
        if project_id is None:
            return
        row = connection.execute(
            """
            SELECT division_id FROM portfolio.projects
            WHERE project_id = %s AND organization_id = %s AND workspace_id = %s
            """,
            (project_id, actor.organization_id, workspace_id),
        ).fetchone()
        if row is None or (division_id is not None and row["division_id"] != division_id):
            raise OperationalNotFound("project was not found in the requested scope")

    @staticmethod
    def _validate_users(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        *user_ids: UUID | None,
    ) -> None:
        supplied = [value for value in user_ids if value is not None]
        if not supplied:
            return
        row = connection.execute(
            """
            SELECT count(*) AS total FROM identity.users
            WHERE organization_id = %s AND user_id = ANY(%s) AND status = 'ACTIVE'
            """,
            (organization_id, supplied),
        ).fetchone()
        if row is None or int(row["total"]) != len(set(supplied)):
            raise OperationalConflict("owner or assignee is not an active organization user")

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
