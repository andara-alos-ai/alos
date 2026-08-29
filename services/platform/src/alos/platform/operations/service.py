from uuid import UUID

from alos.platform.operations.models import (
    ApprovalClaim,
    ApprovalOperationalView,
    CapaAssignment,
    CapaOperationalView,
    CapaTransition,
    DeadlineEvaluation,
    DeadlineEvaluationResult,
    ExceptionOperationalView,
    ExceptionTransition,
    ReminderView,
    WorkItemClaim,
    WorkItemDeadlineUpdate,
    WorkItemDelegate,
    WorkItemOperationalView,
    WorkQueueScope,
)
from alos.platform.operations.repository import PostgresOperationsRepository
from alos.security import Principal, Role
from alos.security.authorization import require_any_role

_OPERATIONAL_ROLES = (
    Role.DIRECTOR,
    Role.DIVISION_HEAD,
    Role.SALES,
    Role.FINANCE,
    Role.PROPERTY,
    Role.HR,
    Role.LEGAL,
    Role.IT_ADMIN,
)
_READ_ROLES = _OPERATIONAL_ROLES + (Role.AI_EXECUTIVE, Role.AUDITOR)


class OperationalWorkService:
    """Application boundary for deterministic operational work management."""

    def __init__(self, repository: PostgresOperationsRepository) -> None:
        self._repository = repository

    def list_work_queue(
        self,
        principal: Principal,
        scope: WorkQueueScope,
        project_id: UUID | None,
        limit: int,
    ) -> tuple[WorkItemOperationalView, ...]:
        require_any_role(principal, *_READ_ROLES)
        return self._repository.list_work_queue(principal, scope, project_id, limit)

    def claim_work_item(
        self, work_item_id: UUID, command: WorkItemClaim, principal: Principal
    ) -> WorkItemOperationalView:
        require_any_role(principal, *_OPERATIONAL_ROLES)
        return self._repository.claim_work_item(work_item_id, command.reason, principal)

    def delegate_work_item(
        self, work_item_id: UUID, command: WorkItemDelegate, principal: Principal
    ) -> WorkItemOperationalView:
        require_any_role(principal, *_OPERATIONAL_ROLES)
        return self._repository.delegate_work_item(
            work_item_id, command.target_user_id, command.reason, principal
        )

    def release_work_item(
        self, work_item_id: UUID, command: WorkItemClaim, principal: Principal
    ) -> WorkItemOperationalView:
        require_any_role(principal, *_OPERATIONAL_ROLES)
        return self._repository.release_work_item(work_item_id, command.reason, principal)

    def update_deadline(
        self, work_item_id: UUID, command: WorkItemDeadlineUpdate, principal: Principal
    ) -> WorkItemOperationalView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.IT_ADMIN)
        return self._repository.update_deadline(
            work_item_id, command.due_at, command.reason, principal
        )

    def claim_approval(
        self, approval_request_id: UUID, command: ApprovalClaim, principal: Principal
    ) -> ApprovalOperationalView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.FINANCE, Role.LEGAL)
        return self._repository.claim_approval(approval_request_id, command.reason, principal)

    def evaluate_deadlines(
        self, command: DeadlineEvaluation, principal: Principal
    ) -> DeadlineEvaluationResult:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        return self._repository.evaluate_deadlines(
            command.horizon_minutes,
            command.escalation_interval_minutes,
            principal,
        )

    def list_reminders(self, principal: Principal, limit: int) -> tuple[ReminderView, ...]:
        require_any_role(principal, *_READ_ROLES)
        return self._repository.list_reminders(principal, limit)

    def transition_exception(
        self, exception_id: UUID, command: ExceptionTransition, principal: Principal
    ) -> ExceptionOperationalView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.IT_ADMIN)
        return self._repository.transition_exception(exception_id, command, principal)

    def assign_capa(
        self, capa_id: UUID, command: CapaAssignment, principal: Principal
    ) -> CapaOperationalView:
        require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD, Role.IT_ADMIN)
        return self._repository.assign_capa(
            capa_id, command.owner_user_id, command.reason, principal
        )

    def transition_capa(
        self, capa_id: UUID, command: CapaTransition, principal: Principal
    ) -> CapaOperationalView:
        require_any_role(principal, *_OPERATIONAL_ROLES)
        return self._repository.transition_capa(capa_id, command, principal)
