from uuid import UUID

from pydantic import BaseModel

from alos.persistence.query_database import PostgresQueryStore
from alos.platform.read_models import Page, PageRequest, PersonnelChecklistRead
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied, require_any_role

DOMAIN_POLICIES: dict[str, tuple[str, Role]] = {
    "leads": ("SALES_MARKETING", Role.SALES),
    "sales_interactions": ("SALES_MARKETING", Role.SALES),
    "budgets": ("FINANCE", Role.FINANCE),
    "payment_requests": ("FINANCE", Role.FINANCE),
    "site_evidence": ("PROPERTY", Role.PROPERTY),
    "kpi_snapshots": ("PROPERTY", Role.PROPERTY),
    "legal_cases": ("LEGAL", Role.LEGAL),
    "recruitment_requests": ("HR", Role.HR),
}

GOVERNANCE_RESOURCES = {"approvals", "exceptions", "capas"}
SHARED_OPERATIONAL_RESOURCES = {
    "work_items",
    "documents",
    "evidence",
    "workflow_runs",
    "transition_events",
    "agent_runs",
}


class OperationalQueryService:
    def __init__(self, store: PostgresQueryStore) -> None:
        self._store = store

    def list_records[ReadModelT: BaseModel](
        self,
        resource: str,
        model: type[ReadModelT],
        request: PageRequest,
        principal: Principal,
        extra_conditions: dict[str, object] | None = None,
    ) -> Page[ReadModelT]:
        self._authorize(resource, principal)
        rows, total = self._store.list_records(resource, request, principal, extra_conditions)
        return Page[ReadModelT].build([model.model_validate(row) for row in rows], request, total)

    def get_record[ReadModelT: BaseModel](
        self,
        resource: str,
        model: type[ReadModelT],
        record_id: UUID,
        principal: Principal,
    ) -> ReadModelT:
        self._authorize(resource, principal)
        return model.model_validate(self._store.get_record(resource, record_id, principal))

    def get_personnel_checklist(
        self, recruitment_request_id: UUID, principal: Principal
    ) -> PersonnelChecklistRead:
        self._authorize("recruitment_requests", principal)
        self._store.get_record("recruitment_requests", recruitment_request_id, principal)
        return PersonnelChecklistRead.model_validate(
            self._store.get_personnel_checklist(recruitment_request_id, principal)
        )

    @staticmethod
    def _authorize(resource: str, principal: Principal) -> None:
        organization_business_readers = (Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR)
        domain_policy = DOMAIN_POLICIES.get(resource)
        if domain_policy is not None:
            if principal.has_any_role(*organization_business_readers):
                return
            if (
                resource == "recruitment_requests"
                and Role.DIVISION_HEAD in principal.roles
                and principal.division_codes
            ):
                return
            division_code, role = domain_policy
            if role in principal.roles and division_code in principal.division_codes:
                return
            if Role.DIVISION_HEAD in principal.roles and division_code in principal.division_codes:
                return
            raise AuthorizationDenied(f"Akses baca resource {resource} tidak diizinkan")
        if resource == "executive_briefs":
            require_any_role(principal, *organization_business_readers)
            return
        if resource == "audit_entries":
            require_any_role(
                principal, Role.DIRECTOR, Role.AI_EXECUTIVE, Role.IT_ADMIN, Role.AUDITOR
            )
            return
        if resource in GOVERNANCE_RESOURCES:
            require_any_role(
                principal,
                Role.DIRECTOR,
                Role.AI_EXECUTIVE,
                Role.DIVISION_HEAD,
                Role.SALES,
                Role.FINANCE,
                Role.PROPERTY,
                Role.HR,
                Role.LEGAL,
                Role.IT_ADMIN,
                Role.AUDITOR,
            )
            return
        if resource in SHARED_OPERATIONAL_RESOURCES:
            require_any_role(principal, *tuple(Role))
            return
        raise AuthorizationDenied("Resource query tidak diizinkan")
