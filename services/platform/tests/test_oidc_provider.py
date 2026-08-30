import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from alos.security.oidc import (
    GOOGLE_JWKS_ENDPOINT,
    GOOGLE_OAUTH_EXCHANGE_ENDPOINT,
    GoogleOIDCProvider,
    OIDCAuthenticationError,
    pkce_challenge,
)

CLIENT_ID = "alos-client.apps.googleusercontent.com"
CLIENT_SECRET = "synthetic-client-secret"
REDIRECT_URI = "http://localhost:8000/api/v1/auth/oidc/callback/google"


def test_google_authorization_url_uses_minimal_scopes_and_pkce() -> None:
    provider = GoogleOIDCProvider(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)

    target = provider.authorization_url(
        state="state-value",
        nonce="nonce-value",
        code_challenge=pkce_challenge("verifier-value"),
    )

    parsed = urlparse(target)
    parameters = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parameters["scope"] == ["openid email profile"]
    assert parameters["state"] == ["state-value"]
    assert parameters["nonce"] == ["nonce-value"]
    assert parameters["code_challenge_method"] == ["S256"]


@pytest.mark.asyncio
async def test_google_id_token_is_verified_cryptographically() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    now = int(time.time())
    id_token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "sub": "google-subject-123",
            "aud": CLIENT_ID,
            "exp": now + 300,
            "iat": now,
            "nonce": "expected-nonce",
            "email": "Reynald@example.test",
            "email_verified": True,
            "name": "Reynald",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GOOGLE_OAUTH_EXCHANGE_ENDPOINT:
            parameters = parse_qs(request.content.decode())
            assert parameters["code_verifier"] == ["test-verifier"]
            assert parameters["client_secret"] == [CLIENT_SECRET]
            return httpx.Response(200, json={"id_token": id_token})
        if str(request.url) == GOOGLE_JWKS_ENDPOINT:
            return httpx.Response(200, json={"keys": [public_jwk]})
        return httpx.Response(404)

    provider = GoogleOIDCProvider(
        CLIENT_ID,
        CLIENT_SECRET,
        REDIRECT_URI,
        transport=httpx.MockTransport(handler),
    )

    claims = await provider.exchange_and_validate(
        code="authorization-code",
        code_verifier="test-verifier",
        expected_nonce="expected-nonce",
    )

    assert claims.subject == "google-subject-123"
    assert claims.email == "reynald@example.test"
    assert claims.email_verified is True


@pytest.mark.asyncio
async def test_google_id_token_rejects_nonce_replay() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    now = int(time.time())
    id_token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "sub": "google-subject-123",
            "aud": CLIENT_ID,
            "exp": now + 300,
            "iat": now,
            "nonce": "different-nonce",
            "email": "reynald@example.test",
            "email_verified": True,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GOOGLE_OAUTH_EXCHANGE_ENDPOINT:
            return httpx.Response(200, json={"id_token": id_token})
        return httpx.Response(200, json={"keys": [public_jwk]})

    provider = GoogleOIDCProvider(
        CLIENT_ID,
        CLIENT_SECRET,
        REDIRECT_URI,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OIDCAuthenticationError, match="Nonce"):
        await provider.exchange_and_validate(
            code="authorization-code",
            code_verifier="test-verifier",
            expected_nonce="expected-nonce",
        )
