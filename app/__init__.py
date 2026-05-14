"""
SkiTech Backend - Application Factory
app/__init__.py  (also importable as app.main:app)

Run with:
    uvicorn app:app --reload
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
    Path("uploads/property_images").mkdir(parents=True, exist_ok=True)
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

# ── Custom middleware (innermost → outermost) ────────────
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(TenantIsolationMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(LoggingMiddleware)

# ── CORS must be outermost so it handles OPTIONS preflight ─
# Always include these origins; merge with any extras from env var so that
# an accidental or partial ALLOWED_ORIGINS env var can't block requests.
_CORS_ORIGINS = list({
    "https://skitech-iota.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8080",
    "http://localhost:5173",
    *settings.ALLOWED_ORIGINS,
})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Static files (local image storage fallback) ───────────
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Routers ───────────────────────────────────────────────
app.include_router(v1_router, prefix="/api")


@app.get("/health", tags=["Health"])
async def health_check():
    from app.core.database import engine
    from sqlalchemy import text
    db_status = "ok"
    db_error = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "error"
        db_error = f"{type(e).__name__}: {str(e)}"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "db": db_status,
        **({"db_error": db_error} if db_error else {}),
    }
