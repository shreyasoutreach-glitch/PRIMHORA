from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_demo,
    routes_evidence,
    routes_incident,
    routes_merchant,
    routes_metrics,
    routes_import,
    routes_recovery,
    routes_webhooks,
    routes_workspace,
)
from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger("primhora.http")

if not settings.demo_mode:
    if not settings.oidc_issuer or not settings.auth_provider_audience or not settings.oidc_jwks_url:
        raise RuntimeError(
            "DEMO_MODE is false but no complete production authentication provider "
            "configuration is present. System halted."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.demo_mode and settings.demo_bootstrap_on_start:
        from seed.bootstrap import main as bootstrap_demo
        bootstrap_demo()
    yield


app = FastAPI(
    title="Primhora",
    description="Early investigation and exposure mitigation for complex financial incidents.",
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )

app.include_router(routes_incident.router, prefix="/api")
app.include_router(routes_evidence.router, prefix="/api")
app.include_router(routes_merchant.router, prefix="/api")
app.include_router(routes_metrics.router, prefix="/api")
app.include_router(routes_import.router, prefix="/api")
app.include_router(routes_demo.router, prefix="/api")
app.include_router(routes_recovery.router, prefix="/api")
app.include_router(routes_webhooks.router, prefix="/api")
app.include_router(routes_workspace.router, prefix="/api")


def _health_payload(db_ok: bool = True) -> dict:
    return {"status": "ok" if db_ok else "degraded", "service": "primhora", "database": "ok" if db_ok else "unavailable"}


@app.middleware("http")
async def security_headers(request, call_next):
    # Generate the correlation ID server-side. Never trust a caller-supplied
    # value as a log key, and never log query strings or request bodies.
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "http_request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def root():
    return _health_payload()


@app.head("/")
def root_head():
    return None


@app.get("/health")
@app.get("/api/health")
def health_check():
    # Render uses this endpoint for readiness. A static 200 would keep an
    # instance marked healthy even when the production database is unreachable.
    from sqlalchemy import text
    from app.core.database import engine
    from fastapi import HTTPException

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return _health_payload(True)
