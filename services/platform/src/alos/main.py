from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alos import __version__
from alos.config import get_settings
from alos.entrypoints.api import router

settings = get_settings()

app = FastAPI(
    title=settings.application_name,
    version=__version__,
    description="API kendali ALOS, workflow deterministik, dan shared Agent Runtime.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
)
app.include_router(router, prefix=settings.api_prefix)
