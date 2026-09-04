"""Staging password authentication and workspace-scoped identity lookups."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from alos.config import Settings
from alos.identity.models import DivisionCode, HumanRole
from alos.persistence.database import psycopg_url

_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 600_000
_SALT_BYTES = 16
_MAX_LOGIN_FAILURES = 5


class AuthenticationError(RuntimeError):
    """A safe authentication failure which never discloses account state."""


class BootstrapError(RuntimeError):
    """The interactive staging bootstrap could not establish the director account."""


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=512)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class AuthenticationPrincipal(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: str
    display_name: str
    roles: list[HumanRole]
    division_codes: list[DivisionCode]
    workspace_ids: list[UUID]


class WorkspaceSummary(BaseModel):
    workspace_id: UUID
    workspace_key: str
    name: str
    division_code: DivisionCode | None
    access_level: str


class BootstrapResult(BaseModel):
    user_id: UUID
    workspace_id: UUID
    workspace_key: str


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    local, separator, domain = normalized.partition("@")
    if (
        separator != "@"
        or not local
        or not domain
        or "." not in domain
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("a valid email address is required")
    return normalized


def validate_bootstrap_password(password: str) -> None:
    if len(password) < 16:
        raise BootstrapError("password must contain at least 16 characters")
    if len(password) > 256:
        raise BootstrapError("password must not exceed 256 characters")


def hash_password(password: str) -> str:
    validate_bootstrap_password(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return "$".join(
        (
            _HASH_ALGORITHM,
            str(_HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = stored_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return False
    if algorithm != _HASH_ALGORITHM or not 1 <= iterations <= 2_000_000:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


_DUMMY_PASSWORD_HASH = "$".join(
    (
        _HASH_ALGORITHM,
        str(_HASH_ITERATIONS),
        base64.urlsafe_b64encode(b"\x00" * _SALT_BYTES).decode("ascii"),
        base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac(
                "sha256",
                b"ALOS-staging-authentication-dummy-password",
                b"\x00" * _SALT_BYTES,
                _HASH_ITERATIONS,
            )
        ).decode("ascii"),
    )
)


class IdentityAuthenticationRepository:
    """Persisted human authentication; tokens only carry the resulting scoped claims."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def authenticate(self, request: PasswordLoginRequest) -> AuthenticationPrincipal:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT user_record.user_id, user_record.organization_id, user_record.email,
                       user_record.display_name, user_record.status, credential.password_hash,
                       credential.locked_until, credential.locked_until > now() AS is_locked
                FROM identity.users AS user_record
                JOIN identity.user_credentials AS credential
                  ON credential.user_id = user_record.user_id
                WHERE lower(user_record.email) = %s
                ORDER BY user_record.created_at ASC
                LIMIT 2
                """,
                (request.email,),
            ).fetchall()
            if len(row) != 1:
                verify_password(request.password, _DUMMY_PASSWORD_HASH)
                raise AuthenticationError("invalid credentials")
            account = row[0]
            password_valid = verify_password(request.password, account["password_hash"])
            if account["status"] != "ACTIVE" or account["is_locked"] or not password_valid:
                if account["status"] == "ACTIVE" and not account["is_locked"]:
                    self._record_failed_login(connection, account["user_id"])
                raise AuthenticationError("invalid credentials")
            principal = self._principal(connection, account)
            if not principal.roles or not principal.workspace_ids:
                raise AuthenticationError("invalid credentials")
            connection.execute(
                """
                UPDATE identity.user_credentials
                SET failed_attempt_count = 0, locked_until = NULL, last_authenticated_at = now()
                WHERE user_id = %s
                """,
                (principal.user_id,),
            )
            self._append_audit(
                connection,
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                action="SESSION_LOGIN_SUCCEEDED",
                entity_type="USER",
                entity_id=principal.user_id,
                correlation_id=uuid4(),
                reason="Human authenticated with a staging password session",
                metadata={"auth_method": "password"},
            )
            return principal

    def list_workspaces(
        self, *, organization_id: UUID, user_id: UUID
    ) -> list[WorkspaceSummary]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT workspace.workspace_id, workspace.workspace_key, workspace.name,
                       division.code AS division_code, membership.access_level
                FROM workspace.memberships AS membership
                JOIN workspace.workspaces AS workspace
                  ON workspace.workspace_id = membership.workspace_id
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = workspace.division_id
                WHERE membership.user_id = %s AND workspace.organization_id = %s
                  AND workspace.status = 'ACTIVE'
                ORDER BY workspace.name ASC, workspace.workspace_key ASC
                """,
                (user_id, organization_id),
            ).fetchall()
        return [WorkspaceSummary(**row) for row in rows]

    def bootstrap_director(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        workspace_key: str,
        workspace_name: str,
        settings: Settings,
    ) -> BootstrapResult:
        if settings.environment not in {"staging", "production"}:
            raise BootstrapError("director bootstrap is restricted to staging or production")
        normalized_email = normalize_email(email)
        if not display_name.strip() or not workspace_key.strip() or not workspace_name.strip():
            raise BootstrapError("display name and workspace fields are required")
        password_hash = hash_password(password)
        with self._transaction() as connection:
            organization = connection.execute(
                "SELECT organization_id FROM identity.organizations WHERE code = 'ALOS'"
            ).fetchone()
            if organization is None:
                raise BootstrapError("ALOS organization seed is unavailable")
            organization_id = organization["organization_id"]
            division = connection.execute(
                """
                SELECT division_id FROM identity.divisions
                WHERE organization_id = %s AND code = 'IT'
                """,
                (organization_id,),
            ).fetchone()
            if division is None:
                raise BootstrapError("IT division seed is unavailable")
            user = connection.execute(
                """
                INSERT INTO identity.users (organization_id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (organization_id, email)
                DO UPDATE SET display_name = EXCLUDED.display_name, status = 'ACTIVE'
                RETURNING user_id
                """,
                (organization_id, normalized_email, display_name.strip()),
            ).fetchone()
            if user is None:
                raise BootstrapError("director user could not be created")
            user_id = user["user_id"]
            connection.execute(
                """
                INSERT INTO identity.role_assignments (user_id, role_code)
                SELECT %s, 'DIRECTOR'
                WHERE NOT EXISTS (
                    SELECT 1 FROM identity.role_assignments
                    WHERE user_id = %s AND role_code = 'DIRECTOR' AND revoked_at IS NULL
                )
                """,
                (user_id, user_id),
            )
            workspace = connection.execute(
                """
                INSERT INTO workspace.workspaces (organization_id, division_id, workspace_key, name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (organization_id, workspace_key)
                DO UPDATE SET name = EXCLUDED.name, status = 'ACTIVE'
                RETURNING workspace_id, workspace_key
                """,
                (
                    organization_id,
                    division["division_id"],
                    workspace_key.strip().upper(),
                    workspace_name.strip(),
                ),
            ).fetchone()
            if workspace is None:
                raise BootstrapError("governance workspace could not be created")
            workspace_id = workspace["workspace_id"]
            connection.execute(
                """
                INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
                VALUES (%s, %s, 'OWNER')
                ON CONFLICT (workspace_id, user_id)
                DO UPDATE SET access_level = 'OWNER'
                """,
                (workspace_id, user_id),
            )
            connection.execute(
                """
                INSERT INTO identity.user_credentials (user_id, password_hash, failed_attempt_count,
                                                        locked_until, password_changed_at)
                VALUES (%s, %s, 0, NULL, now())
                ON CONFLICT (user_id)
                DO UPDATE SET password_hash = EXCLUDED.password_hash, failed_attempt_count = 0,
                              locked_until = NULL, password_changed_at = now()
                """,
                (user_id, password_hash),
            )
            connection.execute(
                """
                INSERT INTO governance.cost_limits (
                    organization_id, workspace_id, daily_request_limit, daily_output_token_limit,
                    daily_cost_cap_usd
                )
                SELECT %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM governance.cost_limits
                    WHERE organization_id = %s AND workspace_id = %s AND active
                )
                """,
                (
                    organization_id,
                    workspace_id,
                    settings.llm_daily_request_limit,
                    settings.llm_daily_output_token_limit,
                    Decimal(settings.llm_daily_cost_cap_usd),
                    organization_id,
                    workspace_id,
                ),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=user_id,
                action="DIRECTOR_CREDENTIAL_BOOTSTRAPPED",
                entity_type="USER",
                entity_id=user_id,
                correlation_id=uuid4(),
                reason="Staging director password was set through the interactive VPS bootstrap",
                metadata={
                    "workspace_id": str(workspace_id),
                    "workspace_key": workspace["workspace_key"],
                },
            )
            return BootstrapResult(
                user_id=user_id, workspace_id=workspace_id, workspace_key=workspace["workspace_key"]
            )

    def bootstrap_it_lead(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        workspace_key: str,
        settings: Settings,
    ) -> BootstrapResult:
        """Create a separate IT Lead login without changing the Director account."""
        if settings.environment not in {"staging", "production"}:
            raise BootstrapError("IT Lead bootstrap is restricted to staging or production")
        normalized_email = normalize_email(email)
        if not display_name.strip() or not workspace_key.strip():
            raise BootstrapError("display name and workspace key are required")
        password_hash = hash_password(password)
        with self._transaction() as connection:
            organization = connection.execute(
                "SELECT organization_id FROM identity.organizations WHERE code = 'ALOS'"
            ).fetchone()
            if organization is None:
                raise BootstrapError("ALOS organization seed is unavailable")
            organization_id = organization["organization_id"]
            division = connection.execute(
                """
                SELECT division_id FROM identity.divisions
                WHERE organization_id = %s AND code = 'IT'
                """,
                (organization_id,),
            ).fetchone()
            if division is None:
                raise BootstrapError("IT division seed is unavailable")
            workspace = connection.execute(
                """
                SELECT workspace_id, workspace_key
                FROM workspace.workspaces
                WHERE organization_id = %s AND workspace_key = %s AND status = 'ACTIVE'
                """,
                (organization_id, workspace_key.strip().upper()),
            ).fetchone()
            if workspace is None:
                raise BootstrapError(
                    "an active governance workspace is required before IT Lead bootstrap"
                )
            existing = connection.execute(
                """
                SELECT user_id FROM identity.users
                WHERE organization_id = %s AND email = %s
                """,
                (organization_id, normalized_email),
            ).fetchone()
            if existing is not None:
                other_role = connection.execute(
                    """
                    SELECT 1 FROM identity.role_assignments
                    WHERE user_id = %s AND role_code <> 'IT_LEAD' AND revoked_at IS NULL
                    """,
                    (existing["user_id"],),
                ).fetchone()
                if other_role is not None:
                    raise BootstrapError(
                        "email already has a non-IT Lead role; bootstrap a separate IT account"
                    )
            user = connection.execute(
                """
                INSERT INTO identity.users (organization_id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (organization_id, email)
                DO UPDATE SET display_name = EXCLUDED.display_name, status = 'ACTIVE'
                RETURNING user_id
                """,
                (organization_id, normalized_email, display_name.strip()),
            ).fetchone()
            if user is None:
                raise BootstrapError("IT Lead user could not be created")
            user_id = user["user_id"]
            connection.execute(
                """
                INSERT INTO identity.role_assignments (user_id, division_id, role_code)
                SELECT %s, %s, 'IT_LEAD'
                WHERE NOT EXISTS (
                    SELECT 1 FROM identity.role_assignments
                    WHERE user_id = %s AND role_code = 'IT_LEAD' AND revoked_at IS NULL
                )
                """,
                (user_id, division["division_id"], user_id),
            )
            connection.execute(
                """
                INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
                VALUES (%s, %s, 'EDITOR')
                ON CONFLICT (workspace_id, user_id)
                DO UPDATE SET access_level = 'EDITOR'
                """,
                (workspace["workspace_id"], user_id),
            )
            connection.execute(
                """
                INSERT INTO identity.user_credentials (user_id, password_hash, failed_attempt_count,
                                                        locked_until, password_changed_at)
                VALUES (%s, %s, 0, NULL, now())
                ON CONFLICT (user_id)
                DO UPDATE SET password_hash = EXCLUDED.password_hash, failed_attempt_count = 0,
                              locked_until = NULL, password_changed_at = now()
                """,
                (user_id, password_hash),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=user_id,
                action="IT_LEAD_CREDENTIAL_BOOTSTRAPPED",
                entity_type="USER",
                entity_id=user_id,
                correlation_id=uuid4(),
                reason="Staging IT Lead password was set through the interactive VPS bootstrap",
                metadata={
                    "workspace_id": str(workspace["workspace_id"]),
                    "workspace_key": workspace["workspace_key"],
                },
            )
            return BootstrapResult(
                user_id=user_id,
                workspace_id=workspace["workspace_id"],
                workspace_key=workspace["workspace_key"],
            )

    @staticmethod
    def _record_failed_login(connection: psycopg.Connection[Any], user_id: UUID) -> None:
        connection.execute(
            """
            UPDATE identity.user_credentials
            SET failed_attempt_count = CASE
                    WHEN failed_attempt_count + 1 >= %s THEN 0
                    ELSE failed_attempt_count + 1
                END,
                locked_until = CASE
                    WHEN failed_attempt_count + 1 >= %s THEN now() + interval '15 minutes'
                    ELSE locked_until
                END
            WHERE user_id = %s
            """,
            (_MAX_LOGIN_FAILURES, _MAX_LOGIN_FAILURES, user_id),
        )

    @staticmethod
    def _principal(
        connection: psycopg.Connection[Any], account: dict[str, Any]
    ) -> AuthenticationPrincipal:
        role_rows = connection.execute(
            """
            SELECT DISTINCT assignment.role_code, division.code AS division_code
            FROM identity.role_assignments AS assignment
            LEFT JOIN identity.divisions AS division
              ON division.division_id = assignment.division_id
            WHERE assignment.user_id = %s AND assignment.revoked_at IS NULL
            ORDER BY assignment.role_code ASC, division.code ASC NULLS LAST
            """,
            (account["user_id"],),
        ).fetchall()
        workspace_rows = connection.execute(
            """
            SELECT membership.workspace_id
            FROM workspace.memberships AS membership
            JOIN workspace.workspaces AS workspace
              ON workspace.workspace_id = membership.workspace_id
            WHERE membership.user_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
            ORDER BY membership.workspace_id ASC
            """,
            (account["user_id"], account["organization_id"]),
        ).fetchall()
        return AuthenticationPrincipal(
            user_id=account["user_id"],
            organization_id=account["organization_id"],
            email=account["email"],
            display_name=account["display_name"],
            roles=sorted({HumanRole(row["role_code"]) for row in role_rows}, key=str),
            division_codes=sorted(
                {DivisionCode(row["division_code"]) for row in role_rows if row["division_code"]},
                key=str,
            ),
            workspace_ids=[row["workspace_id"] for row in workspace_rows],
        )

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, str],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
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
