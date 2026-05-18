"""
SkiTech Backend - Application Factory
app/__init__.py  (also importable as app.main:app)

Run with:
    uvicorn app:app --reload
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.middleware.middleware import (
    AuditMiddleware,
    ErrorHandlerMiddleware,
    LoggingMiddleware,
    TenantIsolationMiddleware,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("skitech")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    try:
        await init_db()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")
    yield
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise hospitality governance platform — merged backend",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=settings.ALLOWED_CREDENTIALS,
    allow_methods=settings.ALLOWED_METHODS,
    allow_headers=settings.ALLOWED_HEADERS,
)

# ── Custom middleware (outermost → innermost) ─────────────
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(TenantIsolationMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(LoggingMiddleware)

# ── Routers ───────────────────────────────────────────────
app.include_router(v1_router, prefix="/api")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }
