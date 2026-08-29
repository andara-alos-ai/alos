from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alos import __version__
from alos.config import get_settings
from alos.entrypoints.api import router
from alos.entrypoints.identity_api import router as identity_router
from alos.entrypoints.query_api import router as query_router

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
app.include_router(router, prefix=settings.api_prefix)
app.include_router(query_router, prefix=settings.api_prefix)
app.include_router(identity_router, prefix=settings.api_prefix)
