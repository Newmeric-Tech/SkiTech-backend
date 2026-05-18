"""
Tests - tests/test_auth.py

Basic smoke tests for auth endpoints.
Uses an in-memory SQLite DB for speed (no Postgres needed).
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_login_invalid(client):
    r = await client.post("/api/v1/auth/login", json={"email": "bad@test.com", "password": "wrong"})
    assert r.status_code == 401


async def test_refresh_invalid_token(client):
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert r.status_code == 401
