import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import jwt

from alos.security.tokens import AuthenticationError

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_EXCHANGE_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


class OIDCAuthenticationError(AuthenticationError):
    """Raised when an OIDC response cannot be trusted or linked."""


@dataclass(frozen=True)
class OIDCIdentityClaims:
    provider: str
    issuer: str
    subject: str
    email: str
    email_verified: bool
    display_name: str
    hosted_domain: str | None


class OIDCProvider(Protocol):
    provider_name: str
    redirect_uri: str

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str: ...

    async def exchange_and_validate(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> OIDCIdentityClaims: ...


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GoogleOIDCProvider:
    provider_name = "google"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        allowed_domain: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._allowed_domain = allowed_domain.casefold() if allowed_domain else None
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        parameters = {
            "client_id": self._client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        if self._allowed_domain:
            parameters["hd"] = self._allowed_domain
        return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"

    async def exchange_and_validate(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> OIDCIdentityClaims:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            response = await client.post(
                GOOGLE_OAUTH_EXCHANGE_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                raise OIDCAuthenticationError("Google menolak kode otorisasi")
            try:
                token_payload: Any = response.json()
            except ValueError as exc:
                raise OIDCAuthenticationError("Respons token Google tidak valid") from exc
            if not isinstance(token_payload, dict):
                raise OIDCAuthenticationError("Respons token Google tidak valid")
            id_token = token_payload.get("id_token")
            if not isinstance(id_token, str) or not id_token:
                raise OIDCAuthenticationError("Google tidak mengembalikan ID token")
            jwks = await self._load_jwks(client)
        return self._validate_id_token(id_token, expected_nonce, jwks)

    async def _load_jwks(self, client: httpx.AsyncClient) -> dict[str, Any]:
        if self._jwks is not None and time.monotonic() < self._jwks_expires_at:
            return self._jwks
        response = await client.get(GOOGLE_JWKS_ENDPOINT, headers={"Accept": "application/json"})
        if response.status_code != 200:
            raise OIDCAuthenticationError("Kunci verifikasi Google tidak tersedia")
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise OIDCAuthenticationError("Kunci verifikasi Google tidak valid") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise OIDCAuthenticationError("Kunci verifikasi Google tidak valid")
        self._jwks = payload
        self._jwks_expires_at = time.monotonic() + 3600
        return payload

    def _validate_id_token(
        self,
        id_token: str,
        expected_nonce: str,
        jwks: dict[str, Any],
    ) -> OIDCIdentityClaims:
        try:
            header = jwt.get_unverified_header(id_token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise OIDCAuthenticationError("Algoritma ID token Google tidak diizinkan")
            matching_key = next(
                (
                    key
                    for key in jwks["keys"]
                    if isinstance(key, dict) and key.get("kid") == header["kid"]
                ),
                None,
            )
            if matching_key is None:
                raise OIDCAuthenticationError("Kunci penandatangan ID token tidak ditemukan")
            signing_key = jwt.PyJWK.from_dict(matching_key).key
            payload = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self._client_id,
                options={
                    "verify_iss": False,
                    "require": ["iss", "sub", "aud", "exp", "iat", "nonce", "email"],
                },
                leeway=30,
            )
        except OIDCAuthenticationError:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise OIDCAuthenticationError("ID token Google tidak valid") from exc

        issuer = payload.get("iss")
        nonce = payload.get("nonce")
        subject = payload.get("sub")
        email = payload.get("email")
        email_verified = payload.get("email_verified")
        hosted_domain = payload.get("hd")
        if issuer not in GOOGLE_ISSUERS:
            raise OIDCAuthenticationError("Issuer ID token Google tidak valid")
        if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
            raise OIDCAuthenticationError("Nonce OIDC tidak valid")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise OIDCAuthenticationError("Subject ID token Google tidak valid")
        if not isinstance(email, str) or not email or len(email) > 254:
            raise OIDCAuthenticationError("Email ID token Google tidak valid")
        if email_verified is not True:
            raise OIDCAuthenticationError("Email Google belum terverifikasi")
        normalized_domain = hosted_domain.casefold() if isinstance(hosted_domain, str) else None
        if self._allowed_domain and normalized_domain != self._allowed_domain:
            raise OIDCAuthenticationError("Akun Google bukan bagian dari domain yang diizinkan")
        name = payload.get("name")
        display_name = name.strip() if isinstance(name, str) and name.strip() else email
        return OIDCIdentityClaims(
            provider=self.provider_name,
            issuer=str(issuer),
            subject=subject,
            email=email.casefold(),
            email_verified=True,
            display_name=display_name[:160],
            hosted_domain=normalized_domain,
        )
