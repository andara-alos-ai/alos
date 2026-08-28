import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from alos.security.models import Principal, Role


class AuthenticationError(ValueError):
    """Raised when a local bearer token is invalid or expired."""


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class TokenCodec:
    """Small HMAC token codec for local development and provider-neutral tests."""

    def __init__(self, secret: str, issuer: str, audience: str) -> None:
        if len(secret) < 24:
            raise ValueError("Rahasia token minimal 24 karakter")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer
        self._audience = audience

    def issue(self, principal: Principal, ttl_seconds: int) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(principal.user_id),
            "org": str(principal.organization_id),
            "roles": sorted(role.value for role in principal.roles),
            "divisions": sorted(principal.division_codes),
            "projects": sorted(str(project_id) for project_id in principal.project_ids),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        }
        body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _encode(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
        return f"alos1.{body}.{signature}"

    def verify(self, token: str) -> Principal:
        try:
            prefix, body, signature = token.split(".")
            expected = _encode(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
            if prefix != "alos1" or not hmac.compare_digest(signature, expected):
                raise AuthenticationError("Tanda tangan token tidak valid")
            payload = json.loads(_decode(body))
            if payload["iss"] != self._issuer or payload["aud"] != self._audience:
                raise AuthenticationError("Issuer atau audience token tidak valid")
            if int(payload["exp"]) <= int(time.time()):
                raise AuthenticationError("Token telah kedaluwarsa")
            return Principal(
                user_id=payload["sub"],
                organization_id=payload["org"],
                roles=frozenset(Role(role) for role in payload["roles"]),
                division_codes=frozenset(payload.get("divisions", [])),
                project_ids=frozenset(payload.get("projects", [])),
            )
        except AuthenticationError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuthenticationError("Format token tidak valid") from exc
