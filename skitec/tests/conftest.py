"""
Test Configuration and Fixtures

Pytest configuration and reusable fixtures for testing.
Includes database setup for async tests.
"""

import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base


# Override database URL for testing
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db():
    """Create test database engine and tables"""
    # Use SQLite for testing or test PostgreSQL database
    test_db_url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(
        test_db_url,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_db):
    """Provide a test database session"""
    async_session_maker = sessionmaker(
        test_db,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_client(db_session):
    """Provide a test client for API endpoints"""
    from fastapi.testclient import TestClient
    from app.main import app

    # Override database dependency
    from app.core.database import get_db_session

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()
