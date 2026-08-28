from uuid import UUID

from alos.security.models import Principal, Role


class AuthorizationDenied(PermissionError):
    """Raised when an authenticated principal lacks business authorization."""


def require_any_role(principal: Principal, *roles: Role) -> None:
    if not principal.has_any_role(*roles):
        allowed = ", ".join(role.value for role in roles)
        raise AuthorizationDenied(f"Peran yang diizinkan: {allowed}")


def require_division_role(principal: Principal, division_code: str, *roles: Role) -> None:
    """Require a business role and membership in the matching division."""
    if division_code not in principal.division_codes or not principal.has_any_role(
        *roles, Role.DIVISION_HEAD
    ):
        allowed = ", ".join(role.value for role in roles)
        raise AuthorizationDenied(
            f"Akses memerlukan divisi {division_code} dan peran: {allowed} atau DIVISION_HEAD"
        )


def require_project_access(principal: Principal, project_id: UUID) -> None:
    if not principal.can_access_project(project_id):
        raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek")
