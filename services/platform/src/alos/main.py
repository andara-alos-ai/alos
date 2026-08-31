from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alos import __version__
from alos.config import get_settings
from alos.entrypoints.agent_runtime_api import router as agent_runtime_router
from alos.entrypoints.api import router
from alos.entrypoints.document_api import router as document_router
from alos.entrypoints.genesis_api import router as genesis_router
from alos.entrypoints.identity_api import router as identity_router
from alos.entrypoints.oidc_api import router as oidc_router
from alos.entrypoints.operations_api import router as operations_router
from alos.entrypoints.query_api import router as query_router
from alos.entrypoints.system_api import router as system_router
from alos.entrypoints.uat_api import router as uat_router
from alos.security.request_limits import RequestBodyLimitMiddleware

settings = get_settings()

app = FastAPI(
    title=settings.application_name,
    version=__version__,
    description="API kendali ALOS, workflow deterministik, dan shared Agent Runtime.",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(oidc_router, prefix=settings.api_prefix)
app.include_router(document_router, prefix=settings.api_prefix)
app.include_router(query_router, prefix=settings.api_prefix)
app.include_router(identity_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)
app.include_router(system_router, prefix=settings.api_prefix)
app.include_router(genesis_router, prefix=settings.api_prefix)
app.include_router(agent_runtime_router, prefix=settings.api_prefix)
app.include_router(uat_router, prefix=settings.api_prefix)
