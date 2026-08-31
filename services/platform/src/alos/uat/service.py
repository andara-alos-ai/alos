from uuid import UUID

from alos.security import Principal, Role
from alos.security.authorization import (
    AuthorizationDenied,
    require_any_role,
    require_division_role,
    require_project_access,
)
from alos.uat.catalog import scenario_by_id
from alos.uat.models import (
    SignoffScope,
    UatCatalog,
    UatRunCreate,
    UatRunView,
    UatScenarioRecord,
    UatSignoffCreate,
)
from alos.uat.repository import PostgresUatRepository

UAT_READER_ROLES = tuple(Role)


class UatService:
    def __init__(self, repository: PostgresUatRepository, catalog: UatCatalog) -> None:
        self._repository = repository
        self._catalog = catalog

    @property
    def catalog(self) -> UatCatalog:
        return self._catalog

    def list_runs(self, project_id: UUID, principal: Principal) -> tuple[UatRunView, ...]:
        require_any_role(principal, *UAT_READER_ROLES)
        require_project_access(principal, project_id)
        return self._repository.list_runs(principal.organization_id, project_id)

    def get_run(self, uat_run_id: UUID, principal: Principal) -> UatRunView:
        require_any_role(principal, *UAT_READER_ROLES)
        run = self._repository.get_run(uat_run_id, principal.organization_id)
        require_project_access(principal, run.project_id)
        return run

    def create_run(self, command: UatRunCreate, principal: Principal) -> UatRunView:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        require_project_access(principal, command.project_id)
        return self._repository.create_run(command, principal)

    def start_run(self, uat_run_id: UUID, principal: Principal) -> UatRunView:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        run = self._repository.get_run(uat_run_id, principal.organization_id)
        require_project_access(principal, run.project_id)
        return self._repository.start_run(uat_run_id, principal)

    def record_scenario(
        self,
        uat_run_id: UUID,
        scenario_id: str,
        command: UatScenarioRecord,
        principal: Principal,
    ) -> UatRunView:
        run = self._repository.get_run(uat_run_id, principal.organization_id)
        require_project_access(principal, run.project_id)
        scenario = scenario_by_id(self._catalog, scenario_id)
        if not principal.roles.intersection(scenario.allowed_roles):
            allowed = ", ".join(sorted(role.value for role in scenario.allowed_roles))
            raise AuthorizationDenied(f"Skenario {scenario_id} memerlukan peran: {allowed}")
        if scenario.division_code and scenario.division_code not in principal.division_codes:
            raise AuthorizationDenied(
                f"Skenario {scenario_id} memerlukan divisi {scenario.division_code}"
            )
        return self._repository.record_scenario(
            uat_run_id, scenario_id, command, principal
        )

    def signoff(
        self,
        uat_run_id: UUID,
        command: UatSignoffCreate,
        principal: Principal,
    ) -> UatRunView:
        run = self._repository.get_run(uat_run_id, principal.organization_id)
        require_project_access(principal, run.project_id)
        signer_role = self._authorize_signoff(command.signoff_scope, principal)
        return self._repository.signoff(uat_run_id, command, signer_role, principal)

    @staticmethod
    def _authorize_signoff(scope: SignoffScope, principal: Principal) -> str:
        if scope == SignoffScope.DIRECTOR:
            require_any_role(principal, Role.DIRECTOR)
            return Role.DIRECTOR.value
        if scope == SignoffScope.AI_EXECUTIVE:
            require_any_role(principal, Role.AI_EXECUTIVE)
            return Role.AI_EXECUTIVE.value
        if scope == SignoffScope.IT and principal.has_any_role(Role.IT_ADMIN):
            if SignoffScope.IT.value not in principal.division_codes:
                raise AuthorizationDenied("Sign-off IT memerlukan konteks divisi IT")
            return Role.IT_ADMIN.value
        require_division_role(
            principal,
            scope.value,
            Role.DIVISION_HEAD,
        )
        if not principal.has_any_role(Role.DIVISION_HEAD):
            raise AuthorizationDenied(
                f"Sign-off {scope.value} harus diberikan Kepala Divisi"
            )
        return Role.DIVISION_HEAD.value
