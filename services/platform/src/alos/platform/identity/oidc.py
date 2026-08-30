import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.persistence.database import PostgresOperationalStore
from alos.security.models import Principal, Role
from alos.security.oidc import (
    OIDCAuthenticationError,
    OIDCIdentityClaims,
    OIDCProvider,
    pkce_challenge,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OIDCLoginTransaction:
    nonce: str
    code_verifier: str


@dataclass(frozen=True)
class OIDCLoginAttempt:
    authorization_url: str
    state: str
    max_age_seconds: int


class PostgresOIDCStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_transaction(
        self,
        *,
        provider: str,
        state: str,
        nonce: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int,
    ) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            self._purge_expired(connection, now)
            connection.execute(
                text(
                    """
                    INSERT INTO identity.oidc_login_transactions
                        (provider, state_digest, nonce, code_verifier, redirect_uri,
                         expires_at, created_at)
                    VALUES (:provider, :state_digest, :nonce, :code_verifier, :redirect_uri,
                            :expires_at, :created_at)
                    """
                ),
                {
                    "provider": provider,
                    "state_digest": _digest(state),
                    "nonce": nonce,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                    "expires_at": now + timedelta(seconds=ttl_seconds),
                    "created_at": now,
                },
            )

    def consume_transaction(self, *, provider: str, state: str) -> OIDCLoginTransaction:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT transaction_id, nonce, code_verifier, redirect_uri, expires_at,
                               consumed_at
                        FROM identity.oidc_login_transactions
                        WHERE provider = :provider AND state_digest = :state_digest
                        FOR UPDATE
                        """
                    ),
                    {"provider": provider, "state_digest": _digest(state)},
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["consumed_at"] is not None or row["expires_at"] <= now:
                raise OIDCAuthenticationError("Transaksi login tidak valid atau kedaluwarsa")
            connection.execute(
                text(
                    """
                    UPDATE identity.oidc_login_transactions
                    SET consumed_at = :consumed_at
                    WHERE transaction_id = :transaction_id
                    """
                ),
                {"consumed_at": now, "transaction_id": row["transaction_id"]},
            )
        return OIDCLoginTransaction(
            nonce=row["nonce"],
            code_verifier=row["code_verifier"],
        )

    def authorize_identity(
        self,
        claims: OIDCIdentityClaims,
        *,
        code_ttl_seconds: int,
    ) -> str:
        now = datetime.now(UTC)
        raw_code = secrets.token_urlsafe(32)
        login_code_id = uuid4()
        with self._engine.begin() as connection:
            self._purge_expired(connection, now)
            identity = self._find_external_identity(
                connection,
                issuer=claims.issuer,
                subject=claims.subject,
            )
            linked_now = False
            if identity is None:
                user = (
                    connection.execute(
                        text(
                            """
                            SELECT user_id, organization_id, email, status
                            FROM identity.users
                            WHERE lower(email) = :email
                            FOR UPDATE
                            """
                        ),
                        {"email": claims.email},
                    )
                    .mappings()
                    .one_or_none()
                )
                if user is None or user["status"] != "ACTIVE":
                    raise OIDCAuthenticationError(
                        "Akun belum diprovisikan atau tidak aktif pada ALOS"
                    )
                identity = self._find_external_identity(
                    connection,
                    issuer=claims.issuer,
                    subject=claims.subject,
                )
                if identity is None:
                    provider_link = (
                        connection.execute(
                            text(
                                """
                                SELECT external_identity_id, issuer, subject
                                FROM identity.external_identities
                                WHERE user_id = :user_id AND provider = :provider
                                FOR UPDATE
                                """
                            ),
                            {"user_id": user["user_id"], "provider": claims.provider},
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if provider_link is not None:
                        raise OIDCAuthenticationError(
                            "Akun ALOS sudah ditautkan ke identitas Google lain"
                        )
                    external_identity_id = uuid4()
                    connection.execute(
                        text(
                            """
                            INSERT INTO identity.external_identities
                                (external_identity_id, user_id, provider, issuer, subject,
                                 email, email_verified, hosted_domain, linked_at, last_login_at)
                            VALUES (:external_identity_id, :user_id, :provider, :issuer, :subject,
                                    :email, true, :hosted_domain, :now, :now)
                            """
                        ),
                        {
                            "external_identity_id": external_identity_id,
                            "user_id": user["user_id"],
                            "provider": claims.provider,
                            "issuer": claims.issuer,
                            "subject": claims.subject,
                            "email": claims.email,
                            "hosted_domain": claims.hosted_domain,
                            "now": now,
                        },
                    )
                    identity = {
                        "external_identity_id": external_identity_id,
                        "user_id": user["user_id"],
                        "organization_id": user["organization_id"],
                        "user_email": user["email"],
                        "status": user["status"],
                    }
                    linked_now = True
            if identity is None:
                raise OIDCAuthenticationError("Identitas Google tidak dapat ditautkan")
            if identity["status"] != "ACTIVE":
                raise OIDCAuthenticationError("Akun ALOS tidak aktif")
            if str(identity["user_email"]).casefold() != claims.email:
                raise OIDCAuthenticationError(
                    "Email Google tidak sama dengan email yang diprovisikan pada ALOS"
                )
            connection.execute(
                text(
                    """
                    UPDATE identity.external_identities
                    SET email = :email, email_verified = true, hosted_domain = :hosted_domain,
                        last_login_at = :last_login_at
                    WHERE external_identity_id = :external_identity_id
                    """
                ),
                {
                    "email": claims.email,
                    "hosted_domain": claims.hosted_domain,
                    "last_login_at": now,
                    "external_identity_id": identity["external_identity_id"],
                },
            )
            principal = self._load_principal(
                connection,
                identity["user_id"],
                identity["organization_id"],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO identity.oidc_login_codes
                        (login_code_id, code_digest, user_id, provider, expires_at, created_at)
                    VALUES (:login_code_id, :code_digest, :user_id, :provider,
                            :expires_at, :created_at)
                    """
                ),
                {
                    "login_code_id": login_code_id,
                    "code_digest": _digest(raw_code),
                    "user_id": principal.user_id,
                    "provider": claims.provider,
                    "expires_at": now + timedelta(seconds=code_ttl_seconds),
                    "created_at": now,
                },
            )
            if linked_now:
                PostgresOperationalStore._append_audit(
                    connection,
                    principal,
                    "identity.oidc_identity_linked",
                    "external_identity",
                    identity["external_identity_id"],
                    uuid4(),
                    None,
                    {"provider": claims.provider, "issuer": claims.issuer},
                    "Identitas eksternal ditautkan setelah login terverifikasi",
                )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.oidc_login_authorized",
                "user",
                principal.user_id,
                uuid4(),
                None,
                {"provider": claims.provider},
                "Login OIDC berhasil diverifikasi",
            )
        return raw_code

    def exchange_login_code(self, raw_code: str) -> Principal:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT lc.login_code_id, lc.user_id, lc.provider, lc.expires_at,
                               lc.consumed_at, u.organization_id, u.status
                        FROM identity.oidc_login_codes lc
                        JOIN identity.users u ON u.user_id = lc.user_id
                        WHERE lc.code_digest = :code_digest
                        FOR UPDATE OF lc, u
                        """
                    ),
                    {"code_digest": _digest(raw_code)},
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["consumed_at"] is not None
                or row["expires_at"] <= now
                or row["status"] != "ACTIVE"
            ):
                raise OIDCAuthenticationError("Kode login tidak valid atau kedaluwarsa")
            connection.execute(
                text(
                    """
                    UPDATE identity.oidc_login_codes
                    SET consumed_at = :consumed_at
                    WHERE login_code_id = :login_code_id
                    """
                ),
                {"consumed_at": now, "login_code_id": row["login_code_id"]},
            )
            principal = self._load_principal(
                connection,
                row["user_id"],
                row["organization_id"],
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "identity.oidc_login_completed",
                "user",
                principal.user_id,
                uuid4(),
                None,
                {"provider": row["provider"]},
                "Kode login OIDC ditukar satu kali",
            )
        return principal

    @staticmethod
    def _find_external_identity(
        connection: Any,
        *,
        issuer: str,
        subject: str,
    ) -> Any:
        return (
            connection.execute(
                text(
                    """
                    SELECT ei.external_identity_id, ei.user_id, u.organization_id,
                           u.email AS user_email, u.status
                    FROM identity.external_identities ei
                    JOIN identity.users u ON u.user_id = ei.user_id
                    WHERE ei.issuer = :issuer AND ei.subject = :subject
                    FOR UPDATE OF ei, u
                    """
                ),
                {"issuer": issuer, "subject": subject},
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _load_principal(
        connection: Any,
        user_id: UUID,
        organization_id: UUID,
    ) -> Principal:
        assignments = connection.execute(
            text(
                """
                SELECT ra.role_code, d.code AS division_code
                FROM identity.role_assignments ra
                LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE ra.user_id = :user_id
                  AND ra.valid_from <= now()
                  AND (ra.valid_until IS NULL OR ra.valid_until > now())
                  AND (d.organization_id IS NULL OR d.organization_id = :organization_id)
                """
            ),
            {"user_id": user_id, "organization_id": organization_id},
        ).mappings()
        assignment_rows = tuple(assignments)
        if not assignment_rows:
            raise OIDCAuthenticationError("Akun ALOS belum memiliki role aktif")
        try:
            roles = frozenset(Role(row["role_code"]) for row in assignment_rows)
        except ValueError as exc:
            raise OIDCAuthenticationError("Akun ALOS memiliki role yang tidak valid") from exc
        divisions = frozenset(
            row["division_code"]
            for row in assignment_rows
            if row["division_code"] is not None
        )
        projects = frozenset(
            connection.execute(
                text(
                    """
                    SELECT pa.project_id
                    FROM identity.project_assignments pa
                    JOIN platform.projects p ON p.project_id = pa.project_id
                    WHERE pa.user_id = :user_id
                      AND p.organization_id = :organization_id
                      AND pa.valid_from <= now()
                      AND (pa.valid_until IS NULL OR pa.valid_until > now())
                    """
                ),
                {"user_id": user_id, "organization_id": organization_id},
            ).scalars()
        )
        return Principal(
            user_id=user_id,
            organization_id=organization_id,
            roles=roles,
            division_codes=divisions,
            project_ids=projects,
        )

    @staticmethod
    def _purge_expired(connection: Any, now: datetime) -> None:
        purge_before = now - timedelta(days=1)
        connection.execute(
            text(
                """
                DELETE FROM identity.oidc_login_transactions
                WHERE expires_at < :purge_before
                   OR (consumed_at IS NOT NULL AND consumed_at < :purge_before)
                """
            ),
            {"purge_before": purge_before},
        )
        connection.execute(
            text(
                """
                DELETE FROM identity.oidc_login_codes
                WHERE expires_at < :purge_before
                   OR (consumed_at IS NOT NULL AND consumed_at < :purge_before)
                """
            ),
            {"purge_before": purge_before},
        )


class OIDCLoginService:
    def __init__(
        self,
        store: PostgresOIDCStore,
        provider: OIDCProvider,
        *,
        transaction_ttl_seconds: int,
        code_ttl_seconds: int,
    ) -> None:
        self._store = store
        self._provider = provider
        self._transaction_ttl_seconds = transaction_ttl_seconds
        self._code_ttl_seconds = code_ttl_seconds

    def begin_login(self) -> OIDCLoginAttempt:
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        self._store.create_transaction(
            provider=self._provider.provider_name,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_uri=self._provider.redirect_uri,
            ttl_seconds=self._transaction_ttl_seconds,
        )
        return OIDCLoginAttempt(
            authorization_url=self._provider.authorization_url(
                state=state,
                nonce=nonce,
                code_challenge=pkce_challenge(code_verifier),
            ),
            state=state,
            max_age_seconds=self._transaction_ttl_seconds,
        )

    async def complete_login(self, *, code: str, state: str) -> str:
        transaction = self._store.consume_transaction(
            provider=self._provider.provider_name,
            state=state,
        )
        claims = await self._provider.exchange_and_validate(
            code=code,
            code_verifier=transaction.code_verifier,
            expected_nonce=transaction.nonce,
        )
        return self._store.authorize_identity(
            claims,
            code_ttl_seconds=self._code_ttl_seconds,
        )

    def exchange_login_code(self, code: str) -> Principal:
        return self._store.exchange_login_code(code)
