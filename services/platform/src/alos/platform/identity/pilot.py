from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, text

from alos.security import Principal, Role

PILOT_EMAIL_DOMAIN = "example.test"
PILOT_ORGANIZATION_CODE = "ARM"
PILOT_PROJECT_CODE = "PILOT-SYN-001"


class PilotBootstrapContext(BaseModel):
    """Non-secret local context required to bootstrap the controlled pilot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    organization_code: str
    project_exists: bool


class PilotProfile(BaseModel):
    """Identity context derived from controlled synthetic assignments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    organization_id: UUID
    email: str
    display_name: str
    roles: frozenset[Role]
    division_codes: frozenset[str]
    project_ids: frozenset[UUID]

    def to_principal(self) -> Principal:
        return Principal(
            user_id=self.user_id,
            organization_id=self.organization_id,
            roles=self.roles,
            division_codes=self.division_codes,
            project_ids=self.project_ids,
        )


class PilotProfileStore:
    """Read-only access to active identities in the controlled pilot project."""

    def __init__(
        self,
        engine: Engine,
        project_code: str = PILOT_PROJECT_CODE,
        email_domain: str = PILOT_EMAIL_DOMAIN,
    ) -> None:
        self._engine = engine
        self._project_code = project_code
        self._email_domain = email_domain.lower()

    def get_bootstrap_context(
        self,
        organization_code: str = PILOT_ORGANIZATION_CODE,
    ) -> PilotBootstrapContext:
        query = text(
            """
            SELECT o.organization_id, o.code AS organization_code,
                   EXISTS (
                     SELECT 1 FROM platform.projects p
                     WHERE p.organization_id = o.organization_id
                       AND p.code = :project_code
                   ) AS project_exists
            FROM identity.organizations o
            WHERE o.code = :organization_code
            """
        )
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    query,
                    {
                        "organization_code": organization_code,
                        "project_code": self._project_code,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError("Organisasi pilot tidak ditemukan")
        return PilotBootstrapContext.model_validate(dict(row))

    def list_profiles(self) -> tuple[PilotProfile, ...]:
        return self._query_profiles()

    def get_profile(self, user_id: UUID) -> PilotProfile:
        profiles = self._query_profiles(user_id)
        if not profiles:
            raise KeyError("Profil pilot tidak ditemukan atau tidak aktif")
        return profiles[0]

    def _query_profiles(self, user_id: UUID | None = None) -> tuple[PilotProfile, ...]:
        user_condition = "AND u.user_id = :user_id" if user_id is not None else ""
        query = text(
            f"""
            SELECT u.user_id, u.organization_id, u.email, u.display_name,
                   array_agg(DISTINCT ra.role_code)
                     FILTER (WHERE ra.role_code IS NOT NULL) AS roles,
                   COALESCE(
                     array_agg(DISTINCT d.code)
                       FILTER (WHERE d.code IS NOT NULL),
                     ARRAY[]::text[]
                   ) AS division_codes,
                   COALESCE(
                     array_agg(DISTINCT pa.project_id)
                       FILTER (WHERE pa.project_id IS NOT NULL),
                     ARRAY[]::uuid[]
                   ) AS project_ids
            FROM identity.users u
            JOIN identity.organizations o ON o.organization_id = u.organization_id
            JOIN platform.projects pilot
              ON pilot.organization_id = o.organization_id
             AND pilot.code = :project_code
             AND pilot.status = 'ACTIVE'
            JOIN identity.role_assignments ra
              ON ra.user_id = u.user_id
             AND ra.valid_from <= now()
             AND (ra.valid_until IS NULL OR ra.valid_until > now())
            LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
            LEFT JOIN identity.project_assignments pa
              ON pa.user_id = u.user_id
             AND pa.valid_from <= now()
             AND (pa.valid_until IS NULL OR pa.valid_until > now())
            LEFT JOIN platform.projects assigned_project
              ON assigned_project.project_id = pa.project_id
             AND assigned_project.organization_id = u.organization_id
            WHERE u.status = 'ACTIVE'
              AND lower(split_part(u.email, '@', 2)) = :email_domain
              AND (pa.project_id IS NULL OR assigned_project.project_id IS NOT NULL)
              {user_condition}
            GROUP BY u.user_id, u.organization_id, u.email, u.display_name
            ORDER BY
              CASE
                WHEN 'DIRECTOR' = ANY(array_agg(ra.role_code)) THEN 1
                WHEN 'AI_EXECUTIVE' = ANY(array_agg(ra.role_code)) THEN 2
                WHEN 'DIVISION_HEAD' = ANY(array_agg(ra.role_code)) THEN 3
                WHEN 'IT_ADMIN' = ANY(array_agg(ra.role_code)) THEN 4
                WHEN 'AUDITOR' = ANY(array_agg(ra.role_code)) THEN 6
                ELSE 5
              END,
              u.display_name
            """  # noqa: S608 -- optional condition is a static clause.
        )
        parameters: dict[str, object] = {
            "project_code": self._project_code,
            "email_domain": self._email_domain,
        }
        if user_id is not None:
            parameters["user_id"] = user_id
        with self._engine.connect() as connection:
            rows = connection.execute(query, parameters).mappings().all()
        return tuple(PilotProfile.model_validate(dict(row)) for row in rows)
