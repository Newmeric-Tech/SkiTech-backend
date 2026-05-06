"""
Database Configuration & Session Management

Initializes SQLAlchemy 2.0 engine and session management.
Provides dependency injection for database sessions.
Supports connection pooling and event listeners for production readiness.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import settings

# Create sync engine with connection pooling
engine = create_engine(
    url=settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://") if settings.DATABASE_URL.startswith("postgresql://") else settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args={
        "application_name": "skitec",
    },
)

# Create session maker
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def get_db_session():
    """
    Dependency injection for database session

    Provides database session to route handlers.
    Automatically handles session cleanup via context manager.

    Yields:
        Session: SQLAlchemy session instance
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """
    Initialize database - Create all tables

    Run this during application startup.
    Uses declarative base metadata from models.
    """
    from ..models.base import Base
    Base.metadata.create_all(bind=engine)


def close_db() -> None:
    """
    Close database connections

    Run this during application shutdown.
    Cleans up connection pools and resources.
    """
    engine.dispose()
