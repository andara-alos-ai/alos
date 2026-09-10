"""System health, metrics, and authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from alos.config import get_settings
from alos.genesis.uploads import object_storage_is_ready
from alos.identity.authentication import (
    AuthenticationError,
    AuthenticationPrincipal,
    PasswordLoginRequest,
)
from alos.persistence.database import database_is_ready
from alos.security.middleware import metrics
from alos.security.tokens import (
    SESSION_COOKIE_NAME,
    ActorContext,
    LocalTokenRequest,
    get_current_actor,
    issue_access_token,
    issue_local_token,
)

router = APIRouter(tags=["system"])


def _main_settings():
    from alos import main as main_module

    return main_module.get_settings()


def _main_identity_repository():
    from alos import main as main_module

    return main_module.get_identity_authentication_repository()


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "alos",
        "environment": settings.environment,
    }


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(content=metrics.prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/health/ready")
def readiness() -> dict[str, str]:
    settings = get_settings()
    if not database_is_ready(settings.database_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not ready",
        )
    if not object_storage_is_ready(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="object storage is not ready",
        )
    return {"status": "ok", "database": "ready", "object_storage": "ready"}


@router.post("/api/v1/auth/local-token")
def create_local_token(request: LocalTokenRequest) -> dict[str, str]:
    return {"access_token": issue_local_token(request, _main_settings()), "token_type": "bearer"}


@router.post("/api/v1/auth/login", response_model=AuthenticationPrincipal)
def login(request: PasswordLoginRequest, response: Response) -> AuthenticationPrincipal:
    """Create an HttpOnly, same-site browser session without returning its token to JavaScript."""
    try:
        principal = _main_identity_repository().authenticate(request)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        ) from error
    settings = _main_settings()
    token = issue_access_token(
        LocalTokenRequest(
            user_id=principal.user_id,
            organization_id=principal.organization_id,
            roles=principal.roles,
            division_codes=principal.division_codes,
            workspace_ids=principal.workspace_ids,
            data_scope=principal.data_scope,
            permissions=principal.permissions,
        ),
        settings,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.environment in {"staging", "production"},
        samesite="lax",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return principal


@router.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=_main_settings().environment in {"staging", "production"},
        samesite="lax",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/api/v1/whoami")
def whoami(actor: Annotated[ActorContext, Depends(get_current_actor)]) -> ActorContext:
    return actor
