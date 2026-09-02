from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status
from pydantic import BaseModel, Field

from alos.config import Settings, get_settings
from alos.identity import DivisionCode, HumanRole


class LocalTokenRequest(BaseModel):
    user_id: UUID
    organization_id: UUID
    roles: list[HumanRole] = Field(min_length=1)
    division_codes: list[DivisionCode] = Field(default_factory=list)
    workspace_ids: list[UUID] = Field(default_factory=list)


class ActorContext(LocalTokenRequest):
    issued_at: datetime
    expires_at: datetime


def issue_local_token(request: LocalTokenRequest, settings: Settings) -> str:
    if settings.environment not in {"local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="local token issuance is disabled outside local/test",
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.auth_token_ttl_seconds)
    claims = {
        "sub": str(request.user_id),
        "organization_id": str(request.organization_id),
        "roles": [role.value for role in request.roles],
        "division_codes": [division.value for division in request.division_codes],
        "workspace_ids": [str(workspace_id) for workspace_id in request.workspace_ids],
        "iat": now,
        "exp": expires_at,
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
    }
    return jwt.encode(
        claims,
        settings.auth_signing_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> ActorContext:
    try:
        claims = jwt.decode(
            token,
            settings.auth_signing_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
        ) from error
    try:
        return ActorContext(
            user_id=claims["sub"],
            organization_id=claims["organization_id"],
            roles=claims["roles"],
            division_codes=claims["division_codes"],
            workspace_ids=claims["workspace_ids"],
            issued_at=datetime.fromtimestamp(claims["iat"], UTC),
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="malformed access token",
        ) from error


def get_current_actor(
    authorization: Annotated[str | None, Header()] = None,
) -> ActorContext:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer token required",
        )
    return decode_access_token(authorization.removeprefix("Bearer "), get_settings())
