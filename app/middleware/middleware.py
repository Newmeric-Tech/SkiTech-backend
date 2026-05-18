"""
Middleware - app/middleware/middleware.py

All middleware in one place:
  - LoggingMiddleware      : logs every request + response time
  - ErrorHandlerMiddleware : converts unhandled exceptions → JSON
  - AuditMiddleware        : records write operations to audit_logs
  - TenantIsolationMiddleware : blocks cross-tenant query param access
"""

import logging
import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.utils.exceptions import SkiTechException

logger = logging.getLogger("skitech")


# ── Logging ───────────────────────────────────────────────

# Skip logging for these paths (documentation & health checks)
_NO_LOG_PATHS = {"/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico"}


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for documentation endpoints
        if request.url.path in _NO_LOG_PATHS:
            return await call_next(request)
        
        start = time.time()
        logger.info(f"→ {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled: {exc}")
            raise

        elapsed = round((time.time() - start) * 1000, 2)
        logger.info(f"← {response.status_code} {request.url.path} [{elapsed}ms]")
        response.headers["X-Process-Time"] = str(elapsed)
        return response


# ── Error Handler ─────────────────────────────────────────

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except SkiTechException as exc:
            logger.warning(f"App error {exc.status_code}: {exc.message}")
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.error_code, "detail": exc.message},
            )
        except Exception as exc:
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": "INTERNAL_SERVER_ERROR", "detail": "An unexpected error occurred"},
            )


# ── Audit ─────────────────────────────────────────────────

# Routes that should be auto-audited (method, path_prefix) → (action, resource, severity)
_AUDITED_ROUTES = {
    ("POST", "/api/v1/auth/register"):   ("CREATE",  "user",      "low"),
    ("POST", "/api/v1/properties"):      ("CREATE",  "property",  "medium"),
    ("PUT",  "/api/v1/properties"):      ("UPDATE",  "property",  "medium"),
    ("DELETE", "/api/v1/properties"):    ("DELETE",  "property",  "high"),
    ("POST", "/api/v1/employees"):       ("CREATE",  "employee",  "low"),
    ("PUT",  "/api/v1/employees"):       ("UPDATE",  "employee",  "low"),
    ("DELETE", "/api/v1/employees"):     ("DELETE",  "employee",  "medium"),
    ("POST", "/api/v1/sop"):             ("CREATE",  "sop",       "low"),
    ("PUT",  "/api/v1/sop"):             ("UPDATE",  "sop",       "low"),
    ("DELETE", "/api/v1/sop"):           ("DELETE",  "sop",       "medium"),
    ("POST", "/api/v1/inventory"):       ("CREATE",  "inventory", "low"),
    ("PUT",  "/api/v1/inventory"):       ("UPDATE",  "inventory", "low"),
    ("DELETE", "/api/v1/inventory"):     ("DELETE",  "inventory", "medium"),
    ("POST", "/api/v1/vendors"):         ("CREATE",  "vendor",    "low"),
    ("PUT",  "/api/v1/vendors"):         ("UPDATE",  "vendor",    "low"),
    ("DELETE", "/api/v1/vendors"):       ("DELETE",  "vendor",    "medium"),
    ("POST", "/api/v1/departments"):     ("CREATE",  "department","low"),
    ("DELETE", "/api/v1/departments"):   ("DELETE",  "department","medium"),
}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if not (200 <= response.status_code < 300):
            return response

        matched = None
        for (method, prefix), info in _AUDITED_ROUTES.items():
            if request.method == method and request.url.path.startswith(prefix):
                matched = info
                break

        if matched:
            action, resource, severity = matched
            user_id = getattr(request.state, "user_id", None)
            tenant_id = getattr(request.state, "tenant_id", None)
            user_email = getattr(request.state, "user_email", "")

            try:
                from app.core.database import AsyncSessionLocal
                from app.models.models import AuditLog
                async with AsyncSessionLocal() as db:
                    log = AuditLog(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        user_email=user_email,
                        action=action,
                        resource_type=resource,
                        severity=severity,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        status="success",
                    )
                    db.add(log)
                    await db.commit()
            except Exception as e:
                logger.warning(f"[AUDIT ERROR] {e}")

        return response


# ── Tenant Isolation ──────────────────────────────────────

_PUBLIC_PATHS = [
    "/api/v1/auth/register", "/api/v1/auth/login",
    "/api/v1/auth/refresh", "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password", "/api/v1/auth/verify-otp",
    "/docs", "/redoc", "/openapi.json", "/health",
]


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip public routes
        if any(request.url.path.startswith(p) for p in _PUBLIC_PATHS):
            return await call_next(request)

        response = await call_next(request)

        token_tenant_id = getattr(request.state, "tenant_id", None)
        if not token_tenant_id:
            return response

        query_tenant_id = request.query_params.get("tenant_id")
        if query_tenant_id and query_tenant_id != str(token_tenant_id):
            return JSONResponse(
                status_code=403,
                content={"detail": "Access forbidden: tenant_id mismatch"},
            )

        return response
