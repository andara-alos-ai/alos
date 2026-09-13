"""Deterministic role, scope, and capability authorization for ALOS resources."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from fastapi import HTTPException, status

from alos.identity import DataScope, DivisionCode, HumanRole
from alos.security.tokens import ActorContext


class AccessMode(StrEnum):
    READ = "READ"
    CREATE_DRAFT = "CREATE_DRAFT"
    UPDATE_SCOPED = "UPDATE_SCOPED"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    EXECUTE_APPROVED_ACTION = "EXECUTE_APPROVED_ACTION"


_DIRECTOR_ROLES = frozenset({HumanRole.DIRECTOR})
_DIVISION_LEAD_ROLES = frozenset({HumanRole.DIVISION_LEAD, HumanRole.DIVISION_OWNER})
_DIVISION_MEMBER_ROLES = frozenset({HumanRole.DIVISION_MEMBER})
_TECHNICAL_ADMIN_ROLES = frozenset({HumanRole.IT_ADMIN, HumanRole.IT_LEAD, HumanRole.AI_ADMIN})


def effective_data_scope(actor: ActorContext) -> DataScope:
    if any(role in _DIRECTOR_ROLES for role in actor.roles):
        return DataScope.COMPANY
    if any(role in _DIVISION_LEAD_ROLES for role in actor.roles):
        return DataScope.DIVISION
    return actor.data_scope


def can_govern_agents(actor: ActorContext) -> bool:
    return any(role in _TECHNICAL_ADMIN_ROLES for role in actor.roles) or bool(
        {"AI_ADMIN", "IT_ADMIN"}.intersection(actor.permissions)
    )


def require_workspace(actor: ActorContext, workspace_id: UUID) -> None:
    if workspace_id not in actor.workspace_ids:
        deny("workspace is outside the authenticated scope")


def require_tenant(actor: ActorContext, tenant_id: UUID | None) -> None:
    """Use only tenant claims established by authentication; absent means un-tenanted data."""
    if tenant_id is None:
        return
    if tenant_id not in actor.tenant_ids:
        deny("tenant is outside the authenticated scope")


def require_division(actor: ActorContext, division_code: DivisionCode | str | None) -> None:
    if division_code is None or effective_data_scope(actor) == DataScope.COMPANY:
        return
    normalized = DivisionCode(division_code)
    if normalized not in actor.division_codes:
        deny("division is outside the authenticated scope")


def require_business_access(
    actor: ActorContext,
    *,
    access_mode: AccessMode,
    workspace_id: UUID | None = None,
    division_code: DivisionCode | str | None = None,
    owner_user_id: UUID | None = None,
    assignee_user_id: UUID | None = None,
) -> None:
    if workspace_id is not None:
        require_workspace(actor, workspace_id)
    require_division(actor, division_code)
    scope = effective_data_scope(actor)
    if (
        scope == DataScope.OWN_ASSIGNED
        and owner_user_id is not None
        and actor.user_id not in {owner_user_id, assignee_user_id}
    ):
        deny("resource is outside the own/assigned scope")
    if access_mode == AccessMode.EXECUTE_APPROVED_ACTION:
        if HumanRole.DIRECTOR not in actor.roles:
            deny("an independent authorized approver is required")
    elif access_mode in {
        AccessMode.CREATE_DRAFT,
        AccessMode.UPDATE_SCOPED,
        AccessMode.REQUEST_APPROVAL,
    }:
        allowed = _DIRECTOR_ROLES | _DIVISION_LEAD_ROLES | _DIVISION_MEMBER_ROLES
        if not any(role in allowed for role in actor.roles):
            deny("role is not permitted to mutate business data")


def require_agent_request(actor: ActorContext, division_code: DivisionCode | str | None) -> None:
    allowed = _DIRECTOR_ROLES | _DIVISION_LEAD_ROLES | _DIVISION_MEMBER_ROLES
    if not any(role in allowed for role in actor.roles):
        deny("role is not permitted to request an agent")
    require_division(actor, division_code)


def deny(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
