"""
S3 (ClientError) and Stripe (StripeError) handlers keep their status codes
but answer a generic detail; the provider's message (bucket names, Stripe
object ids) stays out of the response and the logs, which carry only the
provider's error code. Handlers are called directly with fakes: no network,
no database.
"""
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
import stripe
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.api.v1.endpoints import properties, sop, subscriptions

SECRET = "secret-bucket-or-id-123"


def _logs(caplog):
    return "\n".join(r.getMessage() for r in caplog.records)


def _assert_clean(caplog, info):
    assert SECRET not in _logs(caplog)
    assert SECRET not in str(info.value.detail)


# --- S3 -----------------------------------------------------------------------

class FailingS3:
    def generate_presigned_url(self, *args, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": f"Access to {SECRET} denied"}},
                          "PutObject")


@pytest.fixture
def s3_configured(monkeypatch):
    for mod in (properties, sop):
        monkeypatch.setattr(mod.settings, "AWS_ACCESS_KEY_ID", "k")
        monkeypatch.setattr(mod.settings, "AWS_SECRET_ACCESS_KEY", "s")
        monkeypatch.setattr(mod.boto3, "client", lambda *a, **kw: FailingS3())


async def test_property_upload_url_s3_error_is_generic(s3_configured, monkeypatch, caplog):
    async def found(*args):
        return None
    monkeypatch.setattr(properties, "_get_property_or_404", found)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await properties.get_property_image_upload_url(
                uuid4(), filename="a.png", file_type="image/png", db=None, user={"tenant_id": str(uuid4())})
    assert (info.value.status_code, info.value.detail) == (500, "Could not create the upload URL.")
    assert "code=AccessDenied" in _logs(caplog)
    _assert_clean(caplog, info)


async def test_property_image_upload_s3_error_is_generic(s3_configured, monkeypatch, caplog):
    class PutFailsS3:
        def put_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchBucket", "Message": f"Bucket {SECRET} missing"}},
                              "PutObject")

    class Upload:
        content_type = "image/png"
        filename = "a.png"

        async def read(self):
            return b"png"

    async def found(*args):
        return None
    monkeypatch.setattr(properties, "_get_property_or_404", found)
    monkeypatch.setattr(properties, "_get_s3_client", lambda: PutFailsS3())
    property_id = uuid4()
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await properties.upload_property_image(property_id, file=Upload(), db=None,
                                                   user={"tenant_id": str(uuid4())})
    assert (info.value.status_code, info.value.detail) == (502, "Image storage unavailable. Please try again.")
    logs = _logs(caplog)
    assert f"S3 upload failed for property {property_id} (code=NoSuchBucket)" in logs
    _assert_clean(caplog, info)


def test_sop_upload_url_s3_error_is_generic(s3_configured, caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            sop.get_sop_upload_url(filename="a.pdf", file_type="application/pdf", user={"tenant_id": "t"})
    assert (info.value.status_code, info.value.detail) == (500, "Could not create the upload URL.")
    assert "code=AccessDenied" in _logs(caplog)
    _assert_clean(caplog, info)


# --- Stripe -------------------------------------------------------------------

STRIPE_ERROR = stripe.InvalidRequestError(f"No such object: {SECRET}", "id", code="resource_missing",
                                          http_status=404)
GENERIC_502 = (502, "Payment service error. Please try again.")


def _raise_stripe(*args, **kwargs):
    raise STRIPE_ERROR


class Rows:
    """db.execute() results handed out in order."""

    def __init__(self, *rows):
        self.rows = list(rows)

    async def execute(self, stmt):
        row = self.rows.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: row)


@pytest.fixture
def stripe_configured(monkeypatch):
    monkeypatch.setattr(subscriptions.settings, "STRIPE_SECRET_KEY", "sk_test")


async def test_checkout_stripe_error_is_generic(stripe_configured, monkeypatch, caplog):
    async def customer(*args):
        return "cus_x"
    monkeypatch.setattr(subscriptions, "_get_or_create_stripe_customer", customer)
    monkeypatch.setattr(subscriptions.stripe.checkout.Session, "create", _raise_stripe)
    plan = SimpleNamespace(id=uuid4(), name="Pro", price=10, max_properties=1, max_users=1)
    db = Rows(plan, SimpleNamespace(id=uuid4()))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await subscriptions.create_checkout_session(SimpleNamespace(plan_id=plan.id), db=db,
                                                        user={"tenant_id": str(uuid4())})
    assert (info.value.status_code, info.value.detail) == GENERIC_502
    assert "code=resource_missing http_status=404" in _logs(caplog)
    _assert_clean(caplog, info)


async def test_verify_session_stripe_error_is_generic(stripe_configured, monkeypatch, caplog):
    monkeypatch.setattr(subscriptions.stripe.checkout.Session, "retrieve", _raise_stripe)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await subscriptions.verify_checkout_session({"session_id": "cs_1"}, db=None,
                                                        user={"tenant_id": str(uuid4())})
    assert (info.value.status_code, info.value.detail) == GENERIC_502
    assert "code=resource_missing" in _logs(caplog)
    _assert_clean(caplog, info)


async def test_portal_stripe_error_is_generic(stripe_configured, monkeypatch, caplog):
    monkeypatch.setattr(subscriptions.stripe.billing_portal.Session, "create", _raise_stripe)
    db = Rows(SimpleNamespace(stripe_customer_id="cus_x"))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await subscriptions.create_portal_session(db=db, user={"tenant_id": str(uuid4())})
    assert (info.value.status_code, info.value.detail) == GENERIC_502
    assert "code=resource_missing" in _logs(caplog)
    _assert_clean(caplog, info)
