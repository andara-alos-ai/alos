import hashlib
import os
from uuid import uuid4

import psycopg
import pytest

from alos.config import get_settings
from alos.persistence import Database
from alos.persistence.migrations import psycopg_url
from alos.platform.identity.oidc import OIDCLoginService, PostgresOIDCStore
from alos.security.oidc import OIDCAuthenticationError, OIDCIdentityClaims

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


class FakeGoogleProvider:
    provider_name = "google"
    redirect_uri = "http://localhost:8000/api/v1/auth/oidc/callback/google"

    def __init__(self, claims: OIDCIdentityClaims) -> None:
        self.claims = claims
        self.expected_nonce: str | None = None

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        self.expected_nonce = nonce
        return f"https://accounts.example.test/auth?state={state}&challenge={code_challenge}"

    async def exchange_and_validate(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> OIDCIdentityClaims:
        assert code == "synthetic-google-authorization-code"
        assert len(code_verifier) >= 43
        assert expected_nonce == self.expected_nonce
        return self.claims


@pytest.mark.asyncio
async def test_oidc_login_links_preprovisioned_user_and_blocks_replay() -> None:
    settings = get_settings()
    database_url = psycopg_url(settings.database_url)
    user_id = uuid4()
    email = f"oidc-{uuid4().hex[:10]}@example.test"
    state_digests: list[str] = []

    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
        division_id = connection.execute(
            """
            SELECT division_id FROM identity.divisions
            WHERE organization_id = %s AND code = 'IT'
            """,
            (organization_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO identity.users
                (user_id, organization_id, email, display_name, status)
            VALUES (%s, %s, %s, 'OIDC Synthetic User', 'ACTIVE')
            """,
            (user_id, organization_id, email),
        )
        connection.execute(
            """
            INSERT INTO identity.role_assignments
                (user_id, division_id, role_code, reason)
            VALUES (%s, %s, 'IT_ADMIN', 'Pengujian integrasi OIDC sintetis')
            """,
            (user_id, division_id),
        )
        connection.commit()

    provider = FakeGoogleProvider(
        OIDCIdentityClaims(
            provider="google",
            issuer="https://accounts.google.com",
            subject=f"subject-{uuid4().hex}",
            email=email,
            email_verified=True,
            display_name="OIDC Synthetic User",
            hosted_domain=None,
        )
    )
    store = PostgresOIDCStore(Database(settings.database_url).engine)
    service = OIDCLoginService(
        store,
        provider,
        transaction_ttl_seconds=600,
        code_ttl_seconds=60,
    )

    try:
        attempt = service.begin_login()
        state_digests.append(hashlib.sha256(attempt.state.encode()).hexdigest())
        login_code = await service.complete_login(
            code="synthetic-google-authorization-code",
            state=attempt.state,
        )
        principal = service.exchange_login_code(login_code)

        assert principal.user_id == user_id
        assert principal.organization_id == organization_id
        assert {role.value for role in principal.roles} == {"IT_ADMIN"}
        assert principal.division_codes == frozenset({"IT"})

        with pytest.raises(OIDCAuthenticationError, match="Transaksi login"):
            await service.complete_login(
                code="synthetic-google-authorization-code",
                state=attempt.state,
            )
        with pytest.raises(OIDCAuthenticationError, match="Kode login"):
            service.exchange_login_code(login_code)

        second_attempt = service.begin_login()
        state_digests.append(hashlib.sha256(second_attempt.state.encode()).hexdigest())
        second_login_code = await service.complete_login(
            code="synthetic-google-authorization-code",
            state=second_attempt.state,
        )
        assert service.exchange_login_code(second_login_code).user_id == user_id

        expired_attempt = service.begin_login()
        expired_state_digest = hashlib.sha256(expired_attempt.state.encode()).hexdigest()
        state_digests.append(expired_state_digest)
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE identity.oidc_login_transactions
                SET created_at = now() - interval '2 minutes',
                    expires_at = now() - interval '1 minute'
                WHERE state_digest = %s
                """,
                (expired_state_digest,),
            )
            connection.commit()
        with pytest.raises(OIDCAuthenticationError, match="kedaluwarsa"):
            await service.complete_login(
                code="synthetic-google-authorization-code",
                state=expired_attempt.state,
            )

        expired_login_code = store.authorize_identity(provider.claims, code_ttl_seconds=60)
        expired_code_digest = hashlib.sha256(expired_login_code.encode()).hexdigest()
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE identity.oidc_login_codes
                SET created_at = now() - interval '2 minutes',
                    expires_at = now() - interval '1 minute'
                WHERE code_digest = %s
                """,
                (expired_code_digest,),
            )
            connection.commit()
        with pytest.raises(OIDCAuthenticationError, match="kedaluwarsa"):
            service.exchange_login_code(expired_login_code)

        with psycopg.connect(database_url) as connection:
            identity = connection.execute(
                """
                SELECT external_identity_id, user_id, email_verified
                FROM identity.external_identities
                WHERE issuer = %s AND subject = %s
                """,
                (provider.claims.issuer, provider.claims.subject),
            ).fetchone()
            assert identity is not None
            assert identity[1] == user_id
            assert identity[2] is True
            assert (
                connection.execute(
                    "SELECT count(*) FROM identity.external_identities WHERE user_id = %s",
                    (user_id,),
                ).fetchone()[0]
                == 1
            )
            audit_forks = connection.execute(
                """
                SELECT previous_hash
                FROM audit.entries
                WHERE organization_id = %s
                  AND actor_id = %s
                  AND previous_hash IS NOT NULL
                GROUP BY previous_hash
                HAVING count(*) > 1
                """,
                (organization_id, str(user_id)),
            ).fetchall()
            assert audit_forks == []
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM identity.oidc_login_codes WHERE user_id = %s",
                (user_id,),
            )
            for state_digest in state_digests:
                connection.execute(
                    "DELETE FROM identity.oidc_login_transactions WHERE state_digest = %s",
                    (state_digest,),
                )
            connection.execute(
                "DELETE FROM identity.external_identities WHERE user_id = %s",
                (user_id,),
            )
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s",
                (user_id,),
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))
            connection.commit()


def test_oidc_rejects_identity_that_was_not_preprovisioned() -> None:
    settings = get_settings()
    store = PostgresOIDCStore(Database(settings.database_url).engine)
    claims = OIDCIdentityClaims(
        provider="google",
        issuer="https://accounts.google.com",
        subject=f"unprovisioned-{uuid4().hex}",
        email=f"unprovisioned-{uuid4().hex[:10]}@example.test",
        email_verified=True,
        display_name="Unprovisioned User",
        hosted_domain=None,
    )

    with pytest.raises(OIDCAuthenticationError, match="belum diprovisikan"):
        store.authorize_identity(claims, code_ttl_seconds=60)


def test_oidc_rejects_suspended_preprovisioned_user() -> None:
    settings = get_settings()
    database_url = psycopg_url(settings.database_url)
    user_id = uuid4()
    email = f"suspended-{uuid4().hex[:10]}@example.test"
    claims = OIDCIdentityClaims(
        provider="google",
        issuer="https://accounts.google.com",
        subject=f"suspended-subject-{uuid4().hex}",
        email=email,
        email_verified=True,
        display_name="Suspended OIDC User",
        hosted_domain=None,
    )

    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO identity.users
                (user_id, organization_id, email, display_name, status)
            VALUES (%s, %s, %s, 'Suspended OIDC User', 'SUSPENDED')
            """,
            (user_id, organization_id, email),
        )
        connection.commit()

    try:
        store = PostgresOIDCStore(Database(settings.database_url).engine)
        with pytest.raises(OIDCAuthenticationError, match="tidak aktif"):
            store.authorize_identity(claims, code_ttl_seconds=60)
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))
            connection.commit()
