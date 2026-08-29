from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.persistence.database import PostgresOperationalStore
from alos.platform.operations.models import (
    ApprovalOperationalView,
    CapaOperationalView,
    CapaTransition,
    DeadlineEvaluationResult,
    ExceptionOperationalView,
    ExceptionTransition,
    ReminderView,
    WorkItemOperationalView,
    WorkQueueScope,
)
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied

_TERMINAL_WORK_STATUSES = frozenset({"COMPLETED", "CANCELLED", "FAILED"})
_EXCEPTION_TRANSITIONS = {
    "OPEN": frozenset({"INVESTIGATING", "CAPA_REQUIRED"}),
    "INVESTIGATING": frozenset({"CAPA_REQUIRED", "RESOLVED"}),
    "CAPA_REQUIRED": frozenset({"RESOLVED"}),
    "RESOLVED": frozenset(),
}
_CAPA_TRANSITIONS = {
    "OPEN": frozenset({"ANALYSIS"}),
    "ANALYSIS": frozenset({"ACTION_IN_PROGRESS"}),
    "ACTION_IN_PROGRESS": frozenset({"VERIFICATION"}),
    "VERIFICATION": frozenset({"CLOSED"}),
    "CLOSED": frozenset(),
}


class PostgresOperationsRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_work_queue(
        self,
        principal: Principal,
        scope: WorkQueueScope,
        project_id: UUID | None,
        limit: int,
    ) -> tuple[WorkItemOperationalView, ...]:
        conditions = ["wi.organization_id = :organization_id"]
        parameters: dict[str, Any] = {
            "organization_id": principal.organization_id,
            "user_id": principal.user_id,
            "division_codes": sorted(principal.division_codes),
            "project_ids": [str(item) for item in principal.project_ids],
            "project_id": project_id,
            "limit": limit,
        }
        organization_wide = principal.has_any_role(Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR)
        if not organization_wide:
            if not principal.division_codes:
                return ()
            conditions.append("d.code = ANY(CAST(:division_codes AS text[]))")
            if project_id is not None:
                if not principal.can_access_project(project_id):
                    return ()
                conditions.append("wi.project_id = :project_id")
            elif principal.project_ids:
                conditions.append(
                    "(wi.project_id IS NULL OR wi.project_id = ANY(CAST(:project_ids AS uuid[])))"
                )
            else:
                conditions.append("wi.project_id IS NULL")
        elif project_id is not None:
            conditions.append("wi.project_id = :project_id")

        if scope == WorkQueueScope.MINE:
            conditions.append("wi.owner_user_id = :user_id")
        elif scope == WorkQueueScope.UNASSIGNED:
            conditions.append("wi.owner_user_id IS NULL")
        elif scope == WorkQueueScope.OVERDUE:
            conditions.extend(
                ["wi.due_at < now()", "wi.status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')"]
            )

        where_sql = " AND ".join(conditions)
        query = text(
            f"""
            SELECT wi.work_item_id, wi.organization_id, wi.project_id,
                   d.code AS division_code, wi.title, wi.work_type, wi.priority,
                   wi.status, wi.owner_user_id, wi.claimed_at, wi.due_at,
                   (wi.due_at < now() AND wi.status NOT IN
                    ('COMPLETED', 'CANCELLED', 'FAILED')) AS overdue,
                   wi.escalation_level, wi.escalated_at, wi.correlation_id,
                   wi.created_at, wi.updated_at
            FROM platform.work_items wi
            JOIN identity.divisions d ON d.division_id = wi.division_id
            WHERE {where_sql}
            ORDER BY overdue DESC, wi.due_at NULLS LAST,
                     CASE wi.priority
                       WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                       WHEN 'NORMAL' THEN 3 ELSE 4 END,
                     wi.created_at
            LIMIT :limit
            """  # noqa: S608 -- conditions are selected only from static clauses above.
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query, parameters).mappings()
            return tuple(WorkItemOperationalView.model_validate(dict(row)) for row in rows)

    def claim_work_item(
        self, work_item_id: UUID, reason: str, principal: Principal
    ) -> WorkItemOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._work_item_for_update(connection, work_item_id, principal)
            self._active_actor(connection, principal)
            if row["status"] in _TERMINAL_WORK_STATUSES:
                raise ValueError("Work item terminal tidak dapat diklaim")
            if row["owner_user_id"] not in {None, principal.user_id}:
                raise ValueError("Work item sudah dimiliki pengguna lain")
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET owner_user_id = :user_id, claimed_at = COALESCE(claimed_at, :now),
                        updated_at = :now, version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {"user_id": principal.user_id, "now": now, "work_item_id": work_item_id},
            )
            self._record_assignment(
                connection,
                row,
                principal,
                from_user_id=row["owner_user_id"],
                to_user_id=principal.user_id,
                action="CLAIM",
                reason=reason,
                now=now,
            )
            self._audit_change(
                connection,
                principal,
                "work_item.claimed",
                work_item_id,
                before,
                reason,
                after={"owner_user_id": str(principal.user_id), "claimed_at": now.isoformat()},
            )
            return self._work_item_view(connection, work_item_id)

    def delegate_work_item(
        self,
        work_item_id: UUID,
        target_user_id: UUID,
        reason: str,
        principal: Principal,
    ) -> WorkItemOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._work_item_for_update(connection, work_item_id, principal)
            if row["status"] in _TERMINAL_WORK_STATUSES:
                raise ValueError("Work item terminal tidak dapat didelegasikan")
            manager = principal.has_any_role(Role.DIRECTOR, Role.DIVISION_HEAD)
            if row["owner_user_id"] != principal.user_id and not manager:
                raise AuthorizationDenied(
                    "Hanya owner atau kepala divisi yang dapat mendelegasikan"
                )
            self._eligible_target(connection, row, target_user_id, now)
            if row["owner_user_id"] == target_user_id:
                raise ValueError("Target sudah menjadi owner work item")
            action = "ASSIGN" if row["owner_user_id"] is None else "DELEGATE"
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET owner_user_id = :target_user_id, claimed_at = :now,
                        updated_at = :now, version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {
                    "target_user_id": target_user_id,
                    "now": now,
                    "work_item_id": work_item_id,
                },
            )
            self._record_assignment(
                connection,
                row,
                principal,
                from_user_id=row["owner_user_id"],
                to_user_id=target_user_id,
                action=action,
                reason=reason,
                now=now,
            )
            self._audit_change(
                connection,
                principal,
                "work_item.delegated",
                work_item_id,
                before,
                reason,
                after={"owner_user_id": str(target_user_id), "assignment_action": action},
            )
            return self._work_item_view(connection, work_item_id)

    def release_work_item(
        self, work_item_id: UUID, reason: str, principal: Principal
    ) -> WorkItemOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._work_item_for_update(connection, work_item_id, principal)
            manager = principal.has_any_role(Role.DIRECTOR, Role.DIVISION_HEAD)
            if row["owner_user_id"] != principal.user_id and not manager:
                raise AuthorizationDenied("Hanya owner atau kepala divisi yang dapat melepas tugas")
            if row["owner_user_id"] is None:
                raise ValueError("Work item belum memiliki owner")
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET owner_user_id = NULL, claimed_at = NULL,
                        updated_at = :now, version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {"now": now, "work_item_id": work_item_id},
            )
            self._record_assignment(
                connection,
                row,
                principal,
                from_user_id=row["owner_user_id"],
                to_user_id=None,
                action="RELEASE",
                reason=reason,
                now=now,
            )
            self._audit_change(
                connection,
                principal,
                "work_item.released",
                work_item_id,
                before,
                reason,
                after={"owner_user_id": None},
            )
            return self._work_item_view(connection, work_item_id)

    def update_deadline(
        self,
        work_item_id: UUID,
        due_at: datetime,
        reason: str,
        principal: Principal,
    ) -> WorkItemOperationalView:
        now = datetime.now(UTC)
        if due_at <= now:
            raise ValueError("Deadline baru wajib berada di masa depan")
        with self._engine.begin() as connection:
            row = self._work_item_for_update(connection, work_item_id, principal)
            if row["status"] in _TERMINAL_WORK_STATUSES:
                raise ValueError("Deadline work item terminal tidak dapat diubah")
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE platform.work_items
                    SET due_at = :due_at, last_reminded_at = NULL,
                        escalated_at = NULL, escalation_level = 0,
                        updated_at = :now, version = version + 1
                    WHERE work_item_id = :work_item_id
                    """
                ),
                {"due_at": due_at, "now": now, "work_item_id": work_item_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE platform.reminders SET status = 'CANCELLED'
                    WHERE work_item_id = :work_item_id AND status = 'PENDING'
                    """
                ),
                {"work_item_id": work_item_id},
            )
            self._audit_change(
                connection,
                principal,
                "work_item.deadline_changed",
                work_item_id,
                before,
                reason,
                after={"due_at": due_at.isoformat(), "escalation_level": 0},
            )
            return self._work_item_view(connection, work_item_id)

    def claim_approval(
        self, approval_request_id: UUID, reason: str, principal: Principal
    ) -> ApprovalOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT ar.approval_request_id, ar.work_item_id,
                               ar.requester_user_id, ar.assigned_approver_user_id,
                               ar.status, ar.due_at, ar.claimed_at,
                               ar.escalation_level, wi.project_id,
                               d.code AS division_code, wi.division_id
                        FROM governance.approval_requests ar
                        JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
                        JOIN identity.divisions d ON d.division_id = wi.division_id
                        WHERE ar.approval_request_id = :approval_request_id
                          AND wi.organization_id = :organization_id
                        FOR UPDATE OF ar
                        """
                    ),
                    {
                        "approval_request_id": approval_request_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Approval request tidak ditemukan")
            self._authorize_work_scope(row, principal)
            if row["requester_user_id"] == principal.user_id:
                raise AuthorizationDenied("Pemohon tidak dapat mengambil approval sendiri")
            if row["status"] != "PENDING":
                raise ValueError("Approval request tidak lagi pending")
            if row["assigned_approver_user_id"] not in {None, principal.user_id}:
                raise ValueError("Approval sudah diambil approver lain")
            self._eligible_approver(connection, row, principal, now)
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE governance.approval_requests
                    SET assigned_approver_user_id = :user_id,
                        claimed_at = COALESCE(claimed_at, :now)
                    WHERE approval_request_id = :approval_request_id
                    """
                ),
                {
                    "user_id": principal.user_id,
                    "now": now,
                    "approval_request_id": approval_request_id,
                },
            )
            self._audit_change(
                connection,
                principal,
                "approval.claimed",
                approval_request_id,
                before,
                reason,
                entity_type="approval_request",
                after={"assigned_approver_user_id": str(principal.user_id)},
            )
            return self._approval_view(connection, approval_request_id)

    def evaluate_deadlines(
        self,
        horizon_minutes: int,
        escalation_interval_minutes: int,
        principal: Principal,
    ) -> DeadlineEvaluationResult:
        now = datetime.now(UTC)
        horizon = now + timedelta(minutes=horizon_minutes)
        escalation_cutoff = now - timedelta(minutes=escalation_interval_minutes)
        counters = {
            "work_items_due_soon": 0,
            "work_items_overdue": 0,
            "approvals_due_soon": 0,
            "approvals_overdue": 0,
            "reminders_created": 0,
        }
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE platform.reminders r SET status = 'CANCELLED'
                    WHERE r.organization_id = :organization_id AND r.status = 'PENDING'
                      AND (
                        EXISTS (
                          SELECT 1 FROM platform.work_items wi
                          WHERE wi.work_item_id = r.work_item_id
                            AND wi.status IN ('COMPLETED', 'CANCELLED', 'FAILED')
                        )
                        OR EXISTS (
                          SELECT 1 FROM governance.approval_requests ar
                          WHERE ar.approval_request_id = r.approval_request_id
                            AND ar.status <> 'PENDING'
                        )
                      )
                    """
                ),
                {"organization_id": principal.organization_id},
            )
            work_items = connection.execute(
                text(
                    """
                    SELECT work_item_id, owner_user_id, division_id, due_at,
                           escalation_level, last_reminded_at
                    FROM platform.work_items
                    WHERE organization_id = :organization_id
                      AND due_at IS NOT NULL AND due_at <= :horizon
                      AND status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')
                    FOR UPDATE
                    """
                ),
                {"organization_id": principal.organization_id, "horizon": horizon},
            ).mappings()
            for row in work_items:
                overdue = row["due_at"] < now
                counters["work_items_overdue" if overdue else "work_items_due_soon"] += 1
                reminder_type, level = self._deadline_reminder(
                    overdue=overdue,
                    escalation_level=row["escalation_level"],
                    last_reminded_at=row["last_reminded_at"],
                    escalation_cutoff=escalation_cutoff,
                )
                if reminder_type is None:
                    continue
                if overdue:
                    self._cancel_due_soon_reminder(connection, work_item_id=row["work_item_id"])
                counters["reminders_created"] += self._insert_reminder(
                    connection,
                    principal.organization_id,
                    work_item_id=row["work_item_id"],
                    approval_request_id=None,
                    recipient_user_id=row["owner_user_id"],
                    division_id=row["division_id"],
                    reminder_type=reminder_type,
                    escalation_level=level,
                    now=now,
                )
                connection.execute(
                    text(
                        """
                        UPDATE platform.work_items
                        SET last_reminded_at = :now,
                            escalation_level = :level,
                            escalated_at = CASE WHEN :overdue THEN COALESCE(escalated_at, :now)
                                                ELSE escalated_at END
                        WHERE work_item_id = :work_item_id
                        """
                    ),
                    {
                        "now": now,
                        "level": level,
                        "overdue": overdue,
                        "work_item_id": row["work_item_id"],
                    },
                )

            approvals = connection.execute(
                text(
                    """
                    SELECT ar.approval_request_id, ar.assigned_approver_user_id,
                           ar.due_at, ar.escalation_level, ar.last_reminded_at,
                           wi.division_id
                    FROM governance.approval_requests ar
                    JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
                    WHERE wi.organization_id = :organization_id
                      AND ar.due_at IS NOT NULL AND ar.due_at <= :horizon
                      AND ar.status = 'PENDING'
                    FOR UPDATE OF ar
                    """
                ),
                {"organization_id": principal.organization_id, "horizon": horizon},
            ).mappings()
            for row in approvals:
                overdue = row["due_at"] < now
                counters["approvals_overdue" if overdue else "approvals_due_soon"] += 1
                reminder_type, level = self._deadline_reminder(
                    overdue=overdue,
                    escalation_level=row["escalation_level"],
                    last_reminded_at=row["last_reminded_at"],
                    escalation_cutoff=escalation_cutoff,
                )
                if reminder_type is None:
                    continue
                if overdue:
                    self._cancel_due_soon_reminder(
                        connection, approval_request_id=row["approval_request_id"]
                    )
                counters["reminders_created"] += self._insert_reminder(
                    connection,
                    principal.organization_id,
                    work_item_id=None,
                    approval_request_id=row["approval_request_id"],
                    recipient_user_id=row["assigned_approver_user_id"],
                    division_id=row["division_id"],
                    reminder_type=reminder_type,
                    escalation_level=level,
                    now=now,
                )
                connection.execute(
                    text(
                        """
                        UPDATE governance.approval_requests
                        SET last_reminded_at = :now, escalation_level = :level,
                            escalated_at = CASE WHEN :overdue THEN COALESCE(escalated_at, :now)
                                                ELSE escalated_at END
                        WHERE approval_request_id = :approval_request_id
                        """
                    ),
                    {
                        "now": now,
                        "level": level,
                        "overdue": overdue,
                        "approval_request_id": row["approval_request_id"],
                    },
                )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "operational.deadlines_evaluated",
                "organization",
                principal.organization_id,
                uuid4(),
                None,
                counters,
            )
        return DeadlineEvaluationResult(evaluated_at=now, **counters)

    @staticmethod
    def _deadline_reminder(
        *,
        overdue: bool,
        escalation_level: int,
        last_reminded_at: datetime | None,
        escalation_cutoff: datetime,
    ) -> tuple[str | None, int]:
        if not overdue:
            return "DUE_SOON", escalation_level
        if escalation_level == 0:
            return "OVERDUE", 1
        if escalation_level >= 10 or (
            last_reminded_at is not None and last_reminded_at > escalation_cutoff
        ):
            return None, escalation_level
        return "ESCALATION", escalation_level + 1

    @staticmethod
    def _cancel_due_soon_reminder(
        connection: Any,
        *,
        work_item_id: UUID | None = None,
        approval_request_id: UUID | None = None,
    ) -> None:
        connection.execute(
            text(
                """
                UPDATE platform.reminders SET status = 'CANCELLED'
                WHERE status = 'PENDING' AND reminder_type = 'DUE_SOON'
                  AND (
                    (CAST(:work_item_id AS uuid) IS NOT NULL
                     AND work_item_id = :work_item_id)
                    OR (CAST(:approval_request_id AS uuid) IS NOT NULL
                        AND approval_request_id = :approval_request_id)
                  )
                """
            ),
            {
                "work_item_id": work_item_id,
                "approval_request_id": approval_request_id,
            },
        )

    def list_reminders(self, principal: Principal, limit: int) -> tuple[ReminderView, ...]:
        organization_wide = principal.has_any_role(Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR)
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT r.reminder_id, r.work_item_id, r.approval_request_id,
                           r.recipient_user_id, d.code AS division_code,
                           r.reminder_type, r.escalation_level, r.status,
                           r.scheduled_for, r.created_at
                    FROM platform.reminders r
                    LEFT JOIN identity.divisions d ON d.division_id = r.division_id
                    WHERE r.organization_id = :organization_id
                      AND (
                        CAST(:organization_wide AS boolean)
                        OR r.recipient_user_id = :user_id
                        OR d.code = ANY(CAST(:division_codes AS text[]))
                      )
                    ORDER BY r.scheduled_for, r.created_at
                    LIMIT :limit
                    """
                ),
                {
                    "organization_id": principal.organization_id,
                    "organization_wide": organization_wide,
                    "user_id": principal.user_id,
                    "division_codes": sorted(principal.division_codes),
                    "limit": limit,
                },
            ).mappings()
            return tuple(ReminderView.model_validate(dict(row)) for row in rows)

    def transition_exception(
        self, exception_id: UUID, command: ExceptionTransition, principal: Principal
    ) -> ExceptionOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._exception_for_update(connection, exception_id, principal)
            target = command.target_status.value
            if target not in _EXCEPTION_TRANSITIONS[row["status"]]:
                raise ValueError(f"Transisi exception {row['status']} ke {target} tidak valid")
            if row["owner_user_id"] not in {None, principal.user_id} and not principal.has_any_role(
                Role.DIRECTOR, Role.DIVISION_HEAD
            ):
                raise AuthorizationDenied(
                    "Hanya owner atau kepala divisi yang dapat mengubah exception"
                )
            if target == "RESOLVED":
                self._assert_document_evidence(
                    connection,
                    command.resolution_document_version_id,
                    principal.organization_id,
                    row["project_id"],
                    row["division_id"],
                )
                open_capa = connection.execute(
                    text(
                        """
                        SELECT 1 FROM governance.capas
                        WHERE exception_id = :exception_id AND status <> 'CLOSED'
                        LIMIT 1
                        """
                    ),
                    {"exception_id": exception_id},
                ).first()
                if open_capa is not None:
                    raise ValueError("Exception belum dapat diselesaikan karena CAPA masih terbuka")
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE governance.exceptions
                    SET status = :status,
                        owner_user_id = COALESCE(owner_user_id, :actor_id),
                        resolution_reason = CASE WHEN :status = 'RESOLVED' THEN :reason
                                                 ELSE resolution_reason END,
                        resolution_document_version_id = CASE
                          WHEN :status = 'RESOLVED' THEN :document_version_id
                          ELSE resolution_document_version_id END,
                        resolved_at = CASE WHEN :status = 'RESOLVED' THEN :now
                                           ELSE resolved_at END,
                        updated_at = :now
                    WHERE exception_id = :exception_id
                    """
                ),
                {
                    "status": target,
                    "actor_id": principal.user_id,
                    "reason": command.reason,
                    "document_version_id": command.resolution_document_version_id,
                    "now": now,
                    "exception_id": exception_id,
                },
            )
            self._audit_change(
                connection,
                principal,
                "exception.transitioned",
                exception_id,
                before,
                command.reason,
                entity_type="exception",
                after={
                    "status": target,
                    "resolution_document_version_id": (
                        str(command.resolution_document_version_id)
                        if command.resolution_document_version_id
                        else None
                    ),
                },
            )
            return self._exception_view(connection, exception_id)

    def assign_capa(
        self, capa_id: UUID, owner_user_id: UUID, reason: str, principal: Principal
    ) -> CapaOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._capa_for_update(connection, capa_id, principal)
            if row["status"] == "CLOSED":
                raise ValueError("CAPA yang sudah ditutup tidak dapat ditugaskan ulang")
            required_division_code = None
            if (
                row["division_id"] is None
                and principal.has_any_role(Role.IT_ADMIN)
                and not principal.has_any_role(Role.DIRECTOR)
            ):
                required_division_code = "IT"
            self._eligible_target(
                connection,
                row,
                owner_user_id,
                now,
                required_division_code=required_division_code,
            )
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE governance.capas
                    SET owner_user_id = :owner_user_id, updated_at = :now
                    WHERE capa_id = :capa_id
                    """
                ),
                {"owner_user_id": owner_user_id, "now": now, "capa_id": capa_id},
            )
            self._audit_change(
                connection,
                principal,
                "capa.assigned",
                capa_id,
                before,
                reason,
                "capa",
                after={"owner_user_id": str(owner_user_id)},
            )
            return self._capa_view(connection, capa_id)

    def transition_capa(
        self, capa_id: UUID, command: CapaTransition, principal: Principal
    ) -> CapaOperationalView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._capa_for_update(connection, capa_id, principal)
            target = command.target_status.value
            if target not in _CAPA_TRANSITIONS[row["status"]]:
                raise ValueError(f"Transisi CAPA {row['status']} ke {target} tidak valid")
            manager = principal.has_any_role(Role.DIRECTOR, Role.DIVISION_HEAD)
            if target == "CLOSED":
                if not manager:
                    raise AuthorizationDenied("Penutupan CAPA memerlukan kepala divisi")
                if row["owner_user_id"] == principal.user_id:
                    raise AuthorizationDenied(
                        "Owner CAPA tidak dapat memverifikasi pekerjaannya sendiri"
                    )
                self._assert_document_evidence(
                    connection,
                    command.evidence_document_version_id,
                    principal.organization_id,
                    row["project_id"],
                    row["division_id"],
                )
            elif row["owner_user_id"] != principal.user_id and not manager:
                raise AuthorizationDenied("Hanya owner atau kepala divisi yang dapat mengubah CAPA")
            before = dict(row)
            connection.execute(
                text(
                    """
                    UPDATE governance.capas
                    SET status = :status,
                        reviewer_user_id = CASE WHEN :status = 'CLOSED' THEN :actor_id
                                                ELSE reviewer_user_id END,
                        verification_notes = CASE WHEN :status = 'CLOSED' THEN :notes
                                                   ELSE verification_notes END,
                        evidence_document_version_id = CASE
                          WHEN :status = 'CLOSED' THEN :document_version_id
                          ELSE evidence_document_version_id END,
                        closed_at = CASE WHEN :status = 'CLOSED' THEN :now ELSE closed_at END,
                        updated_at = :now
                    WHERE capa_id = :capa_id
                    """
                ),
                {
                    "status": target,
                    "actor_id": principal.user_id,
                    "notes": command.verification_notes,
                    "document_version_id": command.evidence_document_version_id,
                    "now": now,
                    "capa_id": capa_id,
                },
            )
            self._audit_change(
                connection,
                principal,
                "capa.transitioned",
                capa_id,
                before,
                command.reason,
                "capa",
                after={
                    "status": target,
                    "reviewer_user_id": (str(principal.user_id) if target == "CLOSED" else None),
                    "evidence_document_version_id": (
                        str(command.evidence_document_version_id)
                        if command.evidence_document_version_id
                        else None
                    ),
                },
            )
            return self._capa_view(connection, capa_id)

    @staticmethod
    def _work_item_for_update(connection: Any, work_item_id: UUID, principal: Principal) -> Any:
        row = (
            connection.execute(
                text(
                    """
                    SELECT wi.*, d.code AS division_code
                    FROM platform.work_items wi
                    JOIN identity.divisions d ON d.division_id = wi.division_id
                    WHERE wi.work_item_id = :work_item_id
                      AND wi.organization_id = :organization_id
                    FOR UPDATE OF wi
                    """
                ),
                {"work_item_id": work_item_id, "organization_id": principal.organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Work item tidak ditemukan")
        PostgresOperationsRepository._authorize_work_scope(row, principal)
        return row

    @staticmethod
    def _authorize_work_scope(row: Any, principal: Principal) -> None:
        if row["project_id"] is not None and not principal.can_access_project(row["project_id"]):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke project work item")
        if (
            not principal.has_any_role(Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR)
            and row["division_code"] not in principal.division_codes
        ):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke divisi work item")

    @staticmethod
    def _active_actor(connection: Any, principal: Principal) -> None:
        exists = connection.execute(
            text(
                """
                SELECT 1 FROM identity.users
                WHERE user_id = :user_id AND organization_id = :organization_id
                  AND status = 'ACTIVE'
                """
            ),
            {"user_id": principal.user_id, "organization_id": principal.organization_id},
        ).first()
        if exists is None:
            raise AuthorizationDenied("Pengguna operasional belum aktif")

    @staticmethod
    def _eligible_target(
        connection: Any,
        row: Any,
        user_id: UUID,
        now: datetime,
        *,
        required_division_code: str | None = None,
    ) -> None:
        eligible = connection.execute(
            text(
                """
                SELECT 1
                FROM identity.users u
                JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE u.user_id = :user_id AND u.organization_id = :organization_id
                  AND u.status = 'ACTIVE'
                  AND (CAST(:division_id AS uuid) IS NULL OR d.division_id = :division_id)
                  AND (CAST(:required_division_code AS text) IS NULL
                       OR d.code = :required_division_code)
                  AND ra.valid_from <= :now
                  AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                  AND (
                    CAST(:project_id AS uuid) IS NULL
                    OR EXISTS (
                      SELECT 1 FROM identity.project_assignments pa
                      WHERE pa.user_id = u.user_id AND pa.project_id = :project_id
                        AND pa.valid_from <= :now
                        AND (pa.valid_until IS NULL OR pa.valid_until > :now)
                    )
                  )
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "organization_id": row["organization_id"],
                "division_id": row["division_id"],
                "project_id": row["project_id"],
                "required_division_code": required_division_code,
                "now": now,
            },
        ).first()
        if eligible is None:
            raise AuthorizationDenied("Target tidak aktif pada divisi dan project work item")

    @staticmethod
    def _eligible_approver(connection: Any, row: Any, principal: Principal, now: datetime) -> None:
        eligible = connection.execute(
            text(
                """
                SELECT 1
                FROM identity.users u
                JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE u.user_id = :user_id AND u.organization_id = :organization_id
                  AND u.status = 'ACTIVE' AND ra.valid_from <= :now
                  AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                  AND (
                    ra.role_code = 'DIRECTOR'
                    OR (
                      d.division_id = :division_id
                      AND ra.role_code IN ('DIVISION_HEAD', 'FINANCE', 'LEGAL')
                    )
                  )
                LIMIT 1
                """
            ),
            {
                "user_id": principal.user_id,
                "organization_id": principal.organization_id,
                "division_id": row["division_id"],
                "now": now,
            },
        ).first()
        if eligible is None:
            raise AuthorizationDenied("Pengguna bukan approver aktif untuk divisi ini")

    @staticmethod
    def _record_assignment(
        connection: Any,
        row: Any,
        principal: Principal,
        *,
        from_user_id: UUID | None,
        to_user_id: UUID | None,
        action: str,
        reason: str,
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO platform.work_item_assignments
                    (organization_id, work_item_id, from_user_id, to_user_id,
                     action, reason, assigned_by_user_id, assigned_at)
                VALUES (:organization_id, :work_item_id, :from_user_id, :to_user_id,
                        :action, :reason, :actor_id, :now)
                """
            ),
            {
                "organization_id": row["organization_id"],
                "work_item_id": row["work_item_id"],
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "action": action,
                "reason": reason,
                "actor_id": principal.user_id,
                "now": now,
            },
        )

    @staticmethod
    def _insert_reminder(
        connection: Any,
        organization_id: UUID,
        *,
        work_item_id: UUID | None,
        approval_request_id: UUID | None,
        recipient_user_id: UUID | None,
        division_id: UUID,
        reminder_type: str,
        escalation_level: int,
        now: datetime,
    ) -> int:
        inserted = connection.execute(
            text(
                """
                INSERT INTO platform.reminders
                    (organization_id, work_item_id, approval_request_id,
                     recipient_user_id, division_id, reminder_type,
                     escalation_level, status, scheduled_for, created_at)
                VALUES (:organization_id, :work_item_id, :approval_request_id,
                        :recipient_user_id, :division_id, :reminder_type,
                        :escalation_level, 'PENDING', :now, :now)
                ON CONFLICT DO NOTHING
                RETURNING reminder_id
                """
            ),
            {
                "organization_id": organization_id,
                "work_item_id": work_item_id,
                "approval_request_id": approval_request_id,
                "recipient_user_id": recipient_user_id,
                "division_id": division_id,
                "reminder_type": reminder_type,
                "escalation_level": escalation_level,
                "now": now,
            },
        ).scalar_one_or_none()
        return int(inserted is not None)

    @staticmethod
    def _assert_document_evidence(
        connection: Any,
        document_version_id: UUID | None,
        organization_id: UUID,
        project_id: UUID | None,
        division_id: UUID | None,
    ) -> None:
        exists = connection.execute(
            text(
                """
                SELECT 1
                FROM platform.document_versions dv
                JOIN platform.documents d ON d.document_id = dv.document_id
                WHERE dv.document_version_id = :document_version_id
                  AND d.organization_id = :organization_id
                  AND (d.project_id IS NULL OR d.project_id = :project_id)
                  AND (d.division_id IS NULL OR d.division_id = :division_id)
                """
            ),
            {
                "document_version_id": document_version_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "division_id": division_id,
            },
        ).first()
        if exists is None:
            raise KeyError("Evidence dokumen tidak ditemukan pada scope yang sesuai")

    def _exception_for_update(
        self, connection: Any, exception_id: UUID, principal: Principal
    ) -> Any:
        row = (
            connection.execute(
                text(
                    """
                    SELECT ex.*, wi.project_id, wi.division_id, d.code AS division_code
                    FROM governance.exceptions ex
                    LEFT JOIN platform.work_items wi ON wi.work_item_id = ex.work_item_id
                    LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
                    WHERE ex.exception_id = :exception_id
                      AND ex.organization_id = :organization_id
                    FOR UPDATE OF ex
                    """
                ),
                {"exception_id": exception_id, "organization_id": principal.organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Exception tidak ditemukan")
        if row["work_item_id"] is not None:
            self._authorize_work_scope(row, principal)
        elif not principal.has_any_role(Role.DIRECTOR, Role.IT_ADMIN):
            raise AuthorizationDenied("Exception organisasi hanya dapat dikelola Direktur atau IT")
        return row

    def _capa_for_update(self, connection: Any, capa_id: UUID, principal: Principal) -> Any:
        row = (
            connection.execute(
                text(
                    """
                    SELECT c.*, ex.organization_id, ex.work_item_id,
                           wi.project_id, wi.division_id, d.code AS division_code
                    FROM governance.capas c
                    JOIN governance.exceptions ex ON ex.exception_id = c.exception_id
                    LEFT JOIN platform.work_items wi ON wi.work_item_id = ex.work_item_id
                    LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
                    WHERE c.capa_id = :capa_id AND ex.organization_id = :organization_id
                    FOR UPDATE OF c
                    """
                ),
                {"capa_id": capa_id, "organization_id": principal.organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("CAPA tidak ditemukan")
        if row["work_item_id"] is not None:
            self._authorize_work_scope(row, principal)
        elif not principal.has_any_role(Role.DIRECTOR, Role.IT_ADMIN):
            raise AuthorizationDenied("CAPA organisasi hanya dapat dikelola Direktur atau IT")
        return row

    @staticmethod
    def _work_item_view(connection: Any, work_item_id: UUID) -> WorkItemOperationalView:
        row = (
            connection.execute(
                text(
                    """
                SELECT wi.work_item_id, wi.organization_id, wi.project_id,
                       d.code AS division_code, wi.title, wi.work_type, wi.priority,
                       wi.status, wi.owner_user_id, wi.claimed_at, wi.due_at,
                       (wi.due_at < now() AND wi.status NOT IN
                        ('COMPLETED', 'CANCELLED', 'FAILED')) AS overdue,
                       wi.escalation_level, wi.escalated_at, wi.correlation_id,
                       wi.created_at, wi.updated_at
                FROM platform.work_items wi
                JOIN identity.divisions d ON d.division_id = wi.division_id
                WHERE wi.work_item_id = :work_item_id
                """
                ),
                {"work_item_id": work_item_id},
            )
            .mappings()
            .one()
        )
        return WorkItemOperationalView.model_validate(dict(row))

    @staticmethod
    def _approval_view(connection: Any, approval_request_id: UUID) -> ApprovalOperationalView:
        row = (
            connection.execute(
                text(
                    """
                SELECT approval_request_id, work_item_id, requester_user_id,
                       assigned_approver_user_id, status, due_at, claimed_at,
                       escalation_level
                FROM governance.approval_requests
                WHERE approval_request_id = :approval_request_id
                """
                ),
                {"approval_request_id": approval_request_id},
            )
            .mappings()
            .one()
        )
        return ApprovalOperationalView.model_validate(dict(row))

    @staticmethod
    def _exception_view(connection: Any, exception_id: UUID) -> ExceptionOperationalView:
        row = (
            connection.execute(
                text(
                    """
                SELECT exception_id, status, owner_user_id, resolution_reason,
                       resolution_document_version_id, resolved_at, updated_at
                FROM governance.exceptions WHERE exception_id = :exception_id
                """
                ),
                {"exception_id": exception_id},
            )
            .mappings()
            .one()
        )
        return ExceptionOperationalView.model_validate(dict(row))

    @staticmethod
    def _capa_view(connection: Any, capa_id: UUID) -> CapaOperationalView:
        row = (
            connection.execute(
                text(
                    """
                SELECT capa_id, exception_id, status, owner_user_id,
                       reviewer_user_id, verification_notes,
                       evidence_document_version_id, closed_at, updated_at
                FROM governance.capas WHERE capa_id = :capa_id
                """
                ),
                {"capa_id": capa_id},
            )
            .mappings()
            .one()
        )
        return CapaOperationalView.model_validate(dict(row))

    @staticmethod
    def _audit_change(
        connection: Any,
        principal: Principal,
        action: str,
        entity_id: UUID,
        before: dict[str, Any],
        reason: str,
        entity_type: str = "work_item",
        after: dict[str, Any] | None = None,
    ) -> None:
        after_state = dict(after or {})
        after_state["reason"] = reason
        PostgresOperationalStore._append_audit(
            connection,
            principal,
            action,
            entity_type,
            entity_id,
            uuid4(),
            before,
            after_state,
            reason,
        )
