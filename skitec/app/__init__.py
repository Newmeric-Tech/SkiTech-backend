"""
Skitec Backend Application - Main Application Factory

Initializes and configures the FastAPI application.
Sets up middleware, event handlers, and router inclusion.
Ready for deployment and microservices scaling.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.middleware.audit import AuditMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.logging import LoggingMiddleware

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager

    Handles startup and shutdown events.
    Creates database tables on startup, closes connections on shutdown.
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application

    Returns:
        Configured FastAPI application instance
    """
    # Initialize FastAPI app
    app = FastAPI(
        title=settings.APP_NAME,
        description="Enterprise-grade hospitality governance platform",
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.ALLOWED_CREDENTIALS,
        allow_methods=settings.ALLOWED_METHODS,
        allow_headers=settings.ALLOWED_HEADERS,
    )

    # Add custom middleware (order matters - last added is outermost)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(AuditMiddleware)

    # Include API routers
    app.include_router(v1_router, prefix=settings.API_V1_STR)

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """
        Health check endpoint

        Returns:
            Status information
        """
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """
        Root endpoint

        Returns:
            API information
        """
        return {
            "message": f"Welcome to {settings.APP_NAME}",
            "version": settings.APP_VERSION,
            "docs": "/api/docs",
            "openapi": "/api/openapi.json",
        }

    logger.info("FastAPI application created successfully")
    return app


# Create application instance
app = create_app()
