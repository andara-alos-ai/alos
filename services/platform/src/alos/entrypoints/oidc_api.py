import hmac
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import OperationalError

from alos.config import Settings, get_settings
from alos.persistence import Database
from alos.platform.identity.oidc import OIDCLoginService, PostgresOIDCStore
from alos.security.cookies import set_session_cookies
from alos.security.oidc import GoogleOIDCProvider, OIDCAuthenticationError
from alos.security.tokens import TokenCodec

router = APIRouter()
OIDC_STATE_COOKIE = "alos_oidc_state"

SettingsDependency = Annotated[Settings, Depends(get_settings)]


class OIDCStatusResponse(BaseModel):
    enabled: bool
    provider: Literal["google"] | None


class OIDCExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=32, max_length=256)


class OIDCTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth token type, not a credential.
    expires_in: int


@lru_cache(maxsize=4)
def oidc_service_for_config(
    database_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    allowed_domain: str,
    timeout_seconds: float,
    transaction_ttl_seconds: int,
    login_code_ttl_seconds: int,
) -> OIDCLoginService:
    provider = GoogleOIDCProvider(
        client_id,
        client_secret,
        redirect_uri,
        allowed_domain=allowed_domain or None,
        timeout_seconds=timeout_seconds,
    )
    store = PostgresOIDCStore(Database(database_url).engine)
    return OIDCLoginService(
        store,
        provider,
        transaction_ttl_seconds=transaction_ttl_seconds,
        code_ttl_seconds=login_code_ttl_seconds,
    )


def oidc_service(settings: SettingsDependency) -> OIDCLoginService | None:
    if settings.oidc_provider == "disabled":
        return None
    client_id = (settings.oidc_client_id or "").strip()
    client_secret = settings.oidc_client_secret_value or ""
    return oidc_service_for_config(
        settings.database_url,
        client_id,
        client_secret,
        settings.oidc_redirect_uri,
        settings.oidc_allowed_domain or "",
        settings.oidc_timeout_seconds,
        settings.oidc_transaction_ttl_seconds,
        settings.oidc_login_code_ttl_seconds,
    )


OIDCServiceDependency = Annotated[OIDCLoginService | None, Depends(oidc_service)]


def _require_oidc(service: OIDCLoginService | None) -> OIDCLoginService:
    if service is None:
        raise HTTPException(status_code=404, detail="Login OIDC belum diaktifkan")
    return service


def _login_redirect(
    settings: Settings,
    *,
    code: str | None = None,
    error: str | None = None,
) -> str:
    base = f"{settings.web_origin.rstrip('/')}/login"
    if code:
        return f"{base}#oidc_code={quote(code, safe='')}"
    return f"{base}#oidc_error={quote(error or 'login_failed', safe='')}"


def _redirect_and_clear_cookie(location: str, settings: Settings) -> RedirectResponse:
    response = RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        OIDC_STATE_COOKIE,
        path=f"{settings.api_prefix}/auth/oidc",
        secure=settings.environment in {"staging", "production"},
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/auth/oidc/status", response_model=OIDCStatusResponse, tags=["authentication"])
def oidc_status(settings: SettingsDependency) -> OIDCStatusResponse:
    return OIDCStatusResponse(
        enabled=settings.oidc_provider != "disabled",
        provider="google" if settings.oidc_provider == "google" else None,
    )


@router.get("/auth/oidc/login", tags=["authentication"])
def begin_oidc_login(
    settings: SettingsDependency,
    service_dependency: OIDCServiceDependency,
) -> RedirectResponse:
    service = _require_oidc(service_dependency)
    try:
        attempt = service.begin_login()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Layanan identitas belum tersedia") from exc
    response = RedirectResponse(attempt.authorization_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        OIDC_STATE_COOKIE,
        attempt.state,
        max_age=attempt.max_age_seconds,
        secure=settings.environment in {"staging", "production"},
        httponly=True,
        samesite="lax",
        path=f"{settings.api_prefix}/auth/oidc",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/auth/oidc/callback/google", tags=["authentication"])
async def complete_google_login(
    settings: SettingsDependency,
    service_dependency: OIDCServiceDependency,
    code: Annotated[str | None, Query(max_length=4096)] = None,
    state_value: Annotated[str | None, Query(alias="state", max_length=512)] = None,
    provider_error: Annotated[str | None, Query(alias="error", max_length=120)] = None,
    state_cookie: Annotated[
        str | None,
        Cookie(alias=OIDC_STATE_COOKIE, max_length=512),
    ] = None,
) -> RedirectResponse:
    service = _require_oidc(service_dependency)
    if provider_error:
        return _redirect_and_clear_cookie(
            _login_redirect(settings, error="access_denied"),
            settings,
        )
    if (
        not code
        or not state_value
        or not state_cookie
        or not hmac.compare_digest(state_value, state_cookie)
    ):
        return _redirect_and_clear_cookie(
            _login_redirect(settings, error="invalid_state"),
            settings,
        )
    try:
        login_code = await service.complete_login(code=code, state=state_value)
    except OIDCAuthenticationError:
        return _redirect_and_clear_cookie(
            _login_redirect(settings, error="login_rejected"),
            settings,
        )
    except (httpx.HTTPError, OperationalError):
        return _redirect_and_clear_cookie(
            _login_redirect(settings, error="provider_unavailable"),
            settings,
        )
    return _redirect_and_clear_cookie(
        _login_redirect(settings, code=login_code),
        settings,
    )


@router.post(
    "/auth/oidc/exchange",
    response_model=OIDCTokenResponse,
    tags=["authentication"],
)
def exchange_oidc_login_code(
    request: OIDCExchangeRequest,
    response: Response,
    settings: SettingsDependency,
    service_dependency: OIDCServiceDependency,
) -> OIDCTokenResponse:
    service = _require_oidc(service_dependency)
    try:
        principal = service.exchange_login_code(request.code)
    except OIDCAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Layanan identitas belum tersedia") from exc
    token = TokenCodec(
        settings.auth_signing_secret.get_secret_value(),
        settings.auth_issuer,
        settings.auth_audience,
    ).issue(principal, settings.auth_token_ttl_seconds)
    set_session_cookies(response, token, settings)
    return OIDCTokenResponse(
        access_token=token,
        expires_in=settings.auth_token_ttl_seconds,
    )
