"""
POST /subscriptions/webhook: unsigned events are never processed.

Fake session only; nothing touches a real database or calls Stripe. Valid
signatures are produced with the stripe library's own signing function and a
test secret.
"""
import json
import logging
import time
from types import SimpleNamespace

import httpx
import pytest
import stripe
from fastapi import FastAPI

from app.api.v1.endpoints import subscriptions

TEST_SECRET = "whsec_test_secret"
SUB_ID = "sub_123"
CANCEL_EVENT = json.dumps({
    "id": "evt_1", "object": "event", "type": "customer.subscription.deleted",
    "data": {"object": {"id": SUB_ID, "object": "subscription", "status": "canceled"}},
})


class FakeDB:
    def __init__(self):
        self.sub = SimpleNamespace(stripe_subscription_id=SUB_ID, status="active")
        self.executed = 0
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.executed += 1
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [self.sub]))

    async def commit(self):
        self.commits += 1


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(subscriptions.router)
    app.dependency_overrides[subscriptions.get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _signed_header(payload: str, secret: str) -> str:
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f"{timestamp}.{payload}", secret)
    return f"t={timestamp},v1={signature}"


async def test_secret_unset_returns_503_and_touches_nothing(client, db, monkeypatch, caplog):
    monkeypatch.setattr(subscriptions.settings, "STRIPE_WEBHOOK_SECRET", "")

    with caplog.at_level(logging.ERROR, logger=subscriptions.logger.name):
        async with client:
            # Unparseable body: a 503 (not 400) shows the payload was never parsed.
            bad = await client.post("/subscriptions/webhook", content=b"not json")
            unsigned = await client.post("/subscriptions/webhook", content=CANCEL_EVENT)

    assert bad.status_code == unsigned.status_code == 503
    assert unsigned.json() == {"detail": "Webhook not configured"}
    assert (db.executed, db.commits, db.sub.status) == (0, 0, "active")
    assert "STRIPE_WEBHOOK_SECRET is not set" in caplog.text


async def test_valid_signature_is_processed(client, db, monkeypatch):
    monkeypatch.setattr(subscriptions.settings, "STRIPE_WEBHOOK_SECRET", TEST_SECRET)

    async with client:
        resp = await client.post(
            "/subscriptions/webhook", content=CANCEL_EVENT,
            headers={"stripe-signature": _signed_header(CANCEL_EVENT, TEST_SECRET)},
        )

    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert db.sub.status == "expired" and db.commits == 1


async def test_bad_signature_returns_400(client, db, monkeypatch):
    monkeypatch.setattr(subscriptions.settings, "STRIPE_WEBHOOK_SECRET", TEST_SECRET)

    async with client:
        resp = await client.post(
            "/subscriptions/webhook", content=CANCEL_EVENT,
            headers={"stripe-signature": _signed_header(CANCEL_EVENT, "whsec_wrong")},
        )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Invalid webhook signature"}
    assert (db.executed, db.commits, db.sub.status) == (0, 0, "active")
