from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status

from alos.config import get_settings
from alos.persistence.database import database_is_ready
from alos.security.tokens import (
    ActorContext,
    LocalTokenRequest,
    get_current_actor,
    issue_local_token,
)

app = FastAPI(title="ALOS", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "alos",
        "environment": settings.environment,
    }


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    if not database_is_ready(get_settings().database_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not ready",
        )
    return {"status": "ok", "database": "ready"}


@app.post("/api/v1/auth/local-token")
def create_local_token(request: LocalTokenRequest) -> dict[str, str]:
    return {"access_token": issue_local_token(request, get_settings()), "token_type": "bearer"}


@app.get("/api/v1/whoami")
def whoami(actor: Annotated[ActorContext, Depends(get_current_actor)]) -> ActorContext:
    return actor
