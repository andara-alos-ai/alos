import hmac
import secrets

from fastapi import Response

from alos.config import Settings


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf_token(header_token: str | None, cookie_token: str | None) -> bool:
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token.strip(), cookie_token.strip())


def set_session_cookies(
    response: Response,
    token: str,
    settings: Settings,
    *,
    csrf_token: str | None = None,
) -> str:
    csrf = csrf_token or generate_csrf_token()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.is_session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf,
        max_age=settings.csrf_token_ttl_seconds,
        httponly=False,
        secure=settings.is_session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return csrf


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.is_session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.is_session_cookie_secure,
        httponly=False,
        samesite=settings.session_cookie_samesite,
    )
    response.headers["Cache-Control"] = "no-store"
