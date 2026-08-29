from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.persistence.database import PostgresOperationalStore
from alos.security import (
    Principal,
    ProjectAssignmentCreate,
    ProjectAssignmentView,
    Role,
    RoleAssignmentCreate,
    RoleAssignmentView,
    UserDirectoryPage,
    UserDirectoryView,
    UserStatus,
    UserStatusUpdate,
)
from alos.security.authorization import AuthorizationDenied, require_any_role


class IdentityConflict(ValueError):
    """Raised when an active identity assignment would overlap an existing one."""


class PostgresIdentityStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_users(
        self,
        principal: Principal,
        page: int,
        page_size: int,
        search: str | None,
        status: UserStatus | None,
        role: Role | None,
        division_code: str | None,
    ) -> UserDirectoryPage:
        conditions = ["u.organization_id = :organization_id"]
        parameters: dict[str, Any] = {"organization_id": principal.organization_id}
        if search:
            conditions.append("concat_ws(' ', u.email, u.display_name) ILIKE :search")
            parameters["search"] = f"%{search.strip()}%"
        if status:
            conditions.append("u.status = :status")
            parameters["status"] = status.value
        if role:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM identity.role_assignments raf
                    WHERE raf.user_id = u.user_id AND raf.role_code = :role
                      AND raf.valid_from <= now()
                      AND (raf.valid_until IS NULL OR raf.valid_until > now())
                )
                """
            )
            parameters["role"] = role.value
        if division_code:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM identity.role_assignments rad
                    JOIN identity.divisions dd ON dd.division_id = rad.division_id
                    WHERE rad.user_id = u.user_id AND dd.code = :division_code
                      AND rad.valid_from <= now()
                      AND (rad.valid_until IS NULL OR rad.valid_until > now())
                )
                """
            )
            parameters["division_code"] = division_code
        where_sql = " AND ".join(conditions)
        query = text(
            f"""
            SELECT u.user_id, u.email, u.display_name, u.status, u.created_at, u.updated_at,
                   COALESCE(roles.items, '[]'::jsonb) AS roles,
                   COALESCE(projects.items, '[]'::jsonb) AS projects
            FROM identity.users u
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'assignment_id', ra.assignment_id,
                        'role', ra.role_code,
                        'division_code', d.code,
                        'valid_from', ra.valid_from,
                        'valid_until', ra.valid_until,
                        'reason', ra.reason,
                        'created_at', ra.created_at
                    ) ORDER BY ra.role_code, d.code
                ) AS items
                FROM identity.role_assignments ra
                LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE ra.user_id = u.user_id
                  AND ra.valid_from <= now()
                  AND (ra.valid_until IS NULL OR ra.valid_until > now())
            ) roles ON true
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'assignment_id', pa.assignment_id,
                        'project_id', p.project_id,
                        'project_code', p.code,
                        'project_name', p.name,
                        'valid_from', pa.valid_from,
                        'valid_until', pa.valid_until,
                        'reason', pa.reason,
                        'created_at', pa.created_at
                    ) ORDER BY p.code
                ) AS items
                FROM identity.project_assignments pa
                JOIN platform.projects p ON p.project_id = pa.project_id
                WHERE pa.user_id = u.user_id
                  AND pa.valid_from <= now()
                  AND (pa.valid_until IS NULL OR pa.valid_until > now())
            ) projects ON true
            WHERE {where_sql}
            ORDER BY u.display_name ASC, u.user_id ASC
            LIMIT :limit OFFSET :offset
            """  # noqa: S608 -- conditions are composed from static clauses only.
        )
        count_query = text(
            f"""
            SELECT count(*) FROM identity.users u WHERE {where_sql}
            """  # noqa: S608 -- conditions are composed from static clauses only.
        )
        parameters.update(limit=page_size, offset=(page - 1) * page_size)
        with self._engine.connect() as connection:
            total = int(connection.execute(count_query, parameters).scalar_one())
            rows = connection.execute(query, parameters).mappings().all()
        return UserDirectoryPage(
            items=[UserDirectoryView.model_validate(dict(row)) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )

    def get_user(self, user_id: UUID, principal: Principal) -> UserDirectoryView:
        query = text(
            """
            SELECT u.user_id, u.email, u.display_name, u.status, u.created_at, u.updated_at,
                   COALESCE(roles.items, '[]'::jsonb) AS roles,
                   COALESCE(projects.items, '[]'::jsonb) AS projects
            FROM identity.users u
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                    'assignment_id', ra.assignment_id, 'role', ra.role_code,
                    'division_code', d.code, 'valid_from', ra.valid_from,
                    'valid_until', ra.valid_until, 'reason', ra.reason,
                    'created_at', ra.created_at
                ) ORDER BY ra.role_code, d.code) AS items
                FROM identity.role_assignments ra
                LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE ra.user_id = u.user_id AND ra.valid_from <= now()
                  AND (ra.valid_until IS NULL OR ra.valid_until > now())
            ) roles ON true
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                    'assignment_id', pa.assignment_id, 'project_id', p.project_id,
                    'project_code', p.code, 'project_name', p.name,
                    'valid_from', pa.valid_from, 'valid_until', pa.valid_until,
                    'reason', pa.reason, 'created_at', pa.created_at
                ) ORDER BY p.code) AS items
                FROM identity.project_assignments pa
                JOIN platform.projects p ON p.project_id = pa.project_id
                WHERE pa.user_id = u.user_id AND pa.valid_from <= now()
                  AND (pa.valid_until IS NULL OR pa.valid_until > now())
            ) projects ON true
            WHERE u.organization_id = :organization_id AND u.user_id = :user_id
            """
        )
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    query,
                    {"organization_id": principal.organization_id, "user_id": user_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError("Pengguna tidak ditemukan")
        return UserDirectoryView.model_validate(dict(row))

    def update_status(
        self, user_id: UUID, command: UserStatusUpdate, principal: Principal
    ) -> UserDirectoryView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT user_id, status FROM identity.users
                    WHERE user_id = :user_id AND organization_id = :organization_id
                    FOR UPDATE
                    """
                    ),
                    {"user_id": user_id, "organization_id": principal.organization_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Pengguna tidak ditemukan")
            if row["status"] == command.status.value:
                raise ValueError("Status pengguna sudah sama")
            connection.execute(
                text(
                    """
                    UPDATE identity.users
                    SET status = :status, updated_at = :now, version = version + 1
                    WHERE user_id = :user_id
                    """
                ),
                {"status": command.status.value, "now": now, "user_id": user_id},
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.user_status_changed",
                "user",
                user_id,
                uuid4(),
                {"status": row["status"]},
                {"status": command.status.value},
                command.reason,
            )
        return self.get_user(user_id, principal)

    def add_role_assignment(
        self, user_id: UUID, command: RoleAssignmentCreate, principal: Principal
    ) -> RoleAssignmentView:
        now, assignment_id = datetime.now(UTC), uuid4()
        with self._engine.begin() as connection:
            self._assert_user(connection, user_id, principal)
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
                    raise KeyError("Divisi tidak ditemukan")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(CAST(:user_id AS text)))"),
                {"user_id": user_id},
            )
            duplicate = connection.execute(
                text(
                    """
                    SELECT 1 FROM identity.role_assignments
                    WHERE user_id = :user_id AND role_code = :role_code
                      AND division_id IS NOT DISTINCT FROM :division_id
                      AND valid_from < COALESCE(:valid_until, 'infinity'::timestamptz)
                      AND COALESCE(valid_until, 'infinity'::timestamptz) > :now
                    """
                ),
                {
                    "user_id": user_id,
                    "role_code": command.role.value,
                    "division_id": division_id,
                    "valid_until": command.valid_until,
                    "now": now,
                },
            ).scalar_one_or_none()
            if duplicate is not None:
                raise IdentityConflict("Penugasan role aktif sudah ada pada periode tersebut")
            connection.execute(
                text(
                    """
                    INSERT INTO identity.role_assignments
                        (assignment_id, user_id, division_id, role_code, valid_from,
                         valid_until, reason, created_by, created_at)
                    VALUES (:assignment_id, :user_id, :division_id, :role_code, :now,
                            :valid_until, :reason,
                            (
                                SELECT user_id FROM identity.users
                                WHERE user_id = :created_by
                                  AND organization_id = :organization_id
                            ), :now)
                    """
                ),
                {
                    "assignment_id": assignment_id,
                    "user_id": user_id,
                    "division_id": division_id,
                    "role_code": command.role.value,
                    "valid_until": command.valid_until,
                    "reason": command.reason,
                    "created_by": principal.user_id,
                    "organization_id": principal.organization_id,
                    "now": now,
                },
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.role_assigned",
                "role_assignment",
                assignment_id,
                uuid4(),
                None,
                command.model_dump(mode="json"),
                command.reason,
            )
        return RoleAssignmentView(
            assignment_id=assignment_id,
            role=command.role,
            division_code=command.division_code,
            valid_from=now,
            valid_until=command.valid_until,
            reason=command.reason,
            created_at=now,
        )

    def revoke_role_assignment(
        self, user_id: UUID, assignment_id: UUID, reason: str, principal: Principal
    ) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT ra.assignment_id, ra.role_code, d.code AS division_code
                    FROM identity.role_assignments ra
                    JOIN identity.users u ON u.user_id = ra.user_id
                    LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                    WHERE ra.assignment_id = :assignment_id AND ra.user_id = :user_id
                      AND u.organization_id = :organization_id
                      AND (ra.valid_until IS NULL OR ra.valid_until > :now)
                    FOR UPDATE OF ra
                    """
                    ),
                    {
                        "assignment_id": assignment_id,
                        "user_id": user_id,
                        "organization_id": principal.organization_id,
                        "now": now,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Penugasan role aktif tidak ditemukan")
            connection.execute(
                text(
                    """
                    UPDATE identity.role_assignments SET valid_until = :now
                    WHERE assignment_id = :assignment_id
                    """
                ),
                {"now": now, "assignment_id": assignment_id},
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.role_revoked",
                "role_assignment",
                assignment_id,
                uuid4(),
                dict(row),
                {"valid_until": now.isoformat()},
                reason,
            )

    def add_project_assignment(
        self, user_id: UUID, command: ProjectAssignmentCreate, principal: Principal
    ) -> ProjectAssignmentView:
        now, assignment_id = datetime.now(UTC), uuid4()
        with self._engine.begin() as connection:
            self._assert_user(connection, user_id, principal)
            project = (
                connection.execute(
                    text(
                        """
                    SELECT project_id, code, name FROM platform.projects
                    WHERE project_id = :project_id AND organization_id = :organization_id
                    """
                    ),
                    {
                        "project_id": command.project_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if project is None:
                raise KeyError("Proyek tidak ditemukan")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(CAST(:user_id AS text)))"),
                {"user_id": user_id},
            )
            duplicate = connection.execute(
                text(
                    """
                    SELECT 1 FROM identity.project_assignments
                    WHERE user_id = :user_id AND project_id = :project_id
                      AND valid_from < COALESCE(:valid_until, 'infinity'::timestamptz)
                      AND COALESCE(valid_until, 'infinity'::timestamptz) > :now
                    """
                ),
                {
                    "user_id": user_id,
                    "project_id": command.project_id,
                    "valid_until": command.valid_until,
                    "now": now,
                },
            ).scalar_one_or_none()
            if duplicate is not None:
                raise IdentityConflict("Penugasan proyek aktif sudah ada pada periode tersebut")
            connection.execute(
                text(
                    """
                    INSERT INTO identity.project_assignments
                        (assignment_id, user_id, project_id, valid_from, valid_until,
                         reason, created_by, created_at)
                    VALUES (:assignment_id, :user_id, :project_id, :now, :valid_until,
                            :reason,
                            (
                                SELECT user_id FROM identity.users
                                WHERE user_id = :created_by
                                  AND organization_id = :organization_id
                            ), :now)
                    """
                ),
                {
                    "assignment_id": assignment_id,
                    "user_id": user_id,
                    "project_id": command.project_id,
                    "valid_until": command.valid_until,
                    "reason": command.reason,
                    "created_by": principal.user_id,
                    "organization_id": principal.organization_id,
                    "now": now,
                },
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.project_assigned",
                "project_assignment",
                assignment_id,
                uuid4(),
                None,
                command.model_dump(mode="json"),
                command.reason,
            )
        return ProjectAssignmentView(
            assignment_id=assignment_id,
            project_id=command.project_id,
            project_code=project["code"],
            project_name=project["name"],
            valid_from=now,
            valid_until=command.valid_until,
            reason=command.reason,
            created_at=now,
        )

    def revoke_project_assignment(
        self, user_id: UUID, assignment_id: UUID, reason: str, principal: Principal
    ) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT pa.assignment_id, pa.project_id
                    FROM identity.project_assignments pa
                    JOIN identity.users u ON u.user_id = pa.user_id
                    WHERE pa.assignment_id = :assignment_id AND pa.user_id = :user_id
                      AND u.organization_id = :organization_id
                      AND (pa.valid_until IS NULL OR pa.valid_until > :now)
                    FOR UPDATE OF pa
                    """
                    ),
                    {
                        "assignment_id": assignment_id,
                        "user_id": user_id,
                        "organization_id": principal.organization_id,
                        "now": now,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Penugasan proyek aktif tidak ditemukan")
            connection.execute(
                text(
                    """
                    UPDATE identity.project_assignments SET valid_until = :now
                    WHERE assignment_id = :assignment_id
                    """
                ),
                {"now": now, "assignment_id": assignment_id},
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.project_revoked",
                "project_assignment",
                assignment_id,
                uuid4(),
                dict(row),
                {"valid_until": now.isoformat()},
                reason,
            )

    @staticmethod
    def _assert_user(connection: Any, user_id: UUID, principal: Principal) -> None:
        exists = connection.execute(
            text(
                """
                SELECT 1 FROM identity.users
                WHERE user_id = :user_id AND organization_id = :organization_id
                """
            ),
            {"user_id": user_id, "organization_id": principal.organization_id},
        ).scalar_one_or_none()
        if exists is None:
            raise KeyError("Pengguna tidak ditemukan")


class IdentityService:
    def __init__(self, store: PostgresIdentityStore) -> None:
        self._store = store

    def list_users(
        self,
        principal: Principal,
        page: int,
        page_size: int,
        search: str | None,
        status: UserStatus | None,
        role: Role | None,
        division_code: str | None,
    ) -> UserDirectoryPage:
        self._require_directory_reader(principal)
        return self._store.list_users(
            principal, page, page_size, search, status, role, division_code
        )

    def get_user(self, user_id: UUID, principal: Principal) -> UserDirectoryView:
        self._require_directory_reader(principal)
        return self._store.get_user(user_id, principal)

    def update_status(
        self, user_id: UUID, command: UserStatusUpdate, principal: Principal
    ) -> UserDirectoryView:
        require_any_role(principal, Role.IT_ADMIN)
        if user_id == principal.user_id:
            raise AuthorizationDenied("Administrator tidak dapat mengubah status akunnya sendiri")
        if command.status == UserStatus.INVITED:
            raise ValueError("Status tidak dapat dikembalikan menjadi INVITED")
        return self._store.update_status(user_id, command, principal)

    def add_role_assignment(
        self, user_id: UUID, command: RoleAssignmentCreate, principal: Principal
    ) -> RoleAssignmentView:
        require_any_role(principal, Role.IT_ADMIN)
        self._validate_role_division(command.role, command.division_code)
        self._validate_expiry(command.valid_until)
        return self._store.add_role_assignment(user_id, command, principal)

    def revoke_role_assignment(
        self, user_id: UUID, assignment_id: UUID, reason: str, principal: Principal
    ) -> None:
        require_any_role(principal, Role.IT_ADMIN)
        if user_id == principal.user_id:
            raise AuthorizationDenied("Administrator tidak dapat mencabut role akunnya sendiri")
        self._validate_reason(reason)
        self._store.revoke_role_assignment(user_id, assignment_id, reason, principal)

    def add_project_assignment(
        self, user_id: UUID, command: ProjectAssignmentCreate, principal: Principal
    ) -> ProjectAssignmentView:
        require_any_role(principal, Role.IT_ADMIN)
        self._validate_expiry(command.valid_until)
        return self._store.add_project_assignment(user_id, command, principal)

    def revoke_project_assignment(
        self, user_id: UUID, assignment_id: UUID, reason: str, principal: Principal
    ) -> None:
        require_any_role(principal, Role.IT_ADMIN)
        if user_id == principal.user_id:
            raise AuthorizationDenied("Administrator tidak dapat mencabut akses proyeknya sendiri")
        self._validate_reason(reason)
        self._store.revoke_project_assignment(user_id, assignment_id, reason, principal)

    @staticmethod
    def _require_directory_reader(principal: Principal) -> None:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN, Role.AUDITOR)

    @staticmethod
    def _validate_role_division(role: Role, division_code: str | None) -> None:
        organization_roles = {Role.DIRECTOR, Role.AI_EXECUTIVE, Role.AUDITOR}
        if role in organization_roles and division_code is not None:
            raise ValueError(f"Role {role.value} tidak ditempatkan pada divisi")
        if role == Role.DIVISION_HEAD and division_code is None:
            raise ValueError("Role DIVISION_HEAD wajib memiliki divisi")
        expected_division = {
            Role.SALES: "SALES_MARKETING",
            Role.FINANCE: "FINANCE",
            Role.PROPERTY: "PROPERTY",
            Role.HR: "HR",
            Role.LEGAL: "LEGAL",
            Role.IT_ADMIN: "IT",
        }.get(role)
        if expected_division is not None and division_code != expected_division:
            raise ValueError(f"Role {role.value} hanya dapat ditempatkan pada {expected_division}")

    @staticmethod
    def _validate_expiry(valid_until: datetime | None) -> None:
        if valid_until is not None and valid_until.tzinfo is None:
            raise ValueError("Masa berlaku penugasan wajib menyertakan zona waktu")
        if valid_until is not None and valid_until <= datetime.now(UTC):
            raise ValueError("Masa berlaku penugasan harus berada di masa depan")

    @staticmethod
    def _validate_reason(reason: str) -> None:
        if len(reason.strip()) < 8:
            raise ValueError("Alasan pencabutan minimal 8 karakter")
