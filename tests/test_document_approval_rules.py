"""
Documents:
(a) assign-approver: only Manager, Tenant Admin, Co Admin and Super Admin may
    assign, and the approver can be neither the uploader nor the caller.
(b) signature submit/decline: only the requested signer can act.

assign-approver runs the route with a fake service; the signature checks run
the real service queries on in-memory SQLite. Nothing touches the .env
database.
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.v1.endpoints import documents
from app.models.models import DocumentActivityLog, DocumentSignature
from app.schemas.document_schemas import DocumentSignatureDeclineRequest, DocumentSignatureSubmitRequest
from app.services.document_service import DocumentService

TENANT = uuid4()
UPLOADER = uuid4()


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


# ── (a) assign approver ──────────────────────────────────────────────────────

@pytest.fixture
def fake_service(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            pass

        async def get_document(self, doc_id, tenant_id):
            return SimpleNamespace(id=doc_id, uploaded_by=UPLOADER)

        async def assign_approver(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(**kwargs)

    class Db:
        async def commit(self):
            pass

    monkeypatch.setattr(documents, "DocumentService", Service)
    monkeypatch.setattr(documents, "DocumentApprovalResponse", SimpleNamespace(from_attributes=lambda a: a))
    return calls, Db()


def _user(role):
    return SimpleNamespace(id=uuid4(), tenant_id=TENANT, role_obj=SimpleNamespace(name=role))


async def _assign(db, user, approver_id):
    return await documents.assign_approver(
        document_id=str(uuid4()), request=SimpleNamespace(approver_id=approver_id, approver_role=None),
        current_user=user, db=db)


async def test_staff_cannot_assign_approvers(fake_service):
    calls, db = fake_service

    with pytest.raises(HTTPException) as info:
        await _assign(db, _user("Staff"), uuid4())

    assert info.value.status_code == 403 and calls == []


@pytest.mark.parametrize("role", ["Manager", "Tenant Admin", "Co Admin", "Super Admin"])
async def test_managers_and_admins_can_assign_another_user(fake_service, role):
    calls, db = fake_service
    approver = uuid4()

    await _assign(db, _user(role), approver)

    assert [c["approver_id"] for c in calls] == [approver]


@pytest.mark.parametrize("who", ["uploader", "caller"])
async def test_approver_cannot_be_uploader_or_caller(fake_service, who):
    calls, db = fake_service
    user = _user("Manager")

    with pytest.raises(HTTPException) as info:
        await _assign(db, user, UPLOADER if who == "uploader" else user.id)

    assert info.value.status_code == 400 and calls == []


# ── (b) signatures ───────────────────────────────────────────────────────────

class AsyncSQLite:
    def __init__(self, session):
        self.s = session

    async def execute(self, stmt):
        return self.s.execute(stmt)

    def add(self, obj):
        self.s.add(obj)

    async def flush(self):
        self.s.flush()


@pytest.fixture
def sig_env():
    engine = create_engine("sqlite://")
    DocumentSignature.__table__.create(engine)
    DocumentActivityLog.__table__.create(engine)
    s = Session(engine)
    signer = uuid4()
    sig = DocumentSignature(id=uuid4(), document_id=uuid4(), tenant_id=TENANT, signer_id=signer,
                            signer_name="S", signer_email="s@x.test", signature_status="pending")
    s.add(sig)
    s.commit()
    yield DocumentService(AsyncSQLite(s)), s, sig.id, signer
    s.close()
    engine.dispose()


def _status(s, sig_id):
    s.expire_all()
    return s.execute(select(DocumentSignature.signature_status).where(DocumentSignature.id == sig_id)).scalar_one()


async def test_only_the_signer_can_submit(sig_env):
    service, s, sig_id, signer = sig_env
    request = DocumentSignatureSubmitRequest(signature_image="data:image/png;base64,AAAA")

    assert await service.submit_signature(sig_id, TENANT, uuid4(), request) is None
    assert _status(s, sig_id) == "pending"

    assert await service.submit_signature(sig_id, TENANT, signer, request) is not None
    assert _status(s, sig_id) == "signed"


async def test_only_the_signer_can_decline(sig_env):
    service, s, sig_id, signer = sig_env
    request = DocumentSignatureDeclineRequest(decline_reason="Not my document")

    assert await service.decline_signature(sig_id, TENANT, uuid4(), request) is None
    assert _status(s, sig_id) == "pending"

    assert await service.decline_signature(sig_id, TENANT, signer, request) is not None
    assert _status(s, sig_id) == "rejected"


@pytest.mark.parametrize("action", ["submit", "decline"])
async def test_routes_pass_the_caller_as_signer_and_404_otherwise(monkeypatch, action):
    seen = []

    class Service:
        def __init__(self, db):
            pass

        async def submit_signature(self, sig_id, tenant_id, signer_id, request):
            seen.append(signer_id)

        decline_signature = submit_signature

    monkeypatch.setattr(documents, "DocumentService", Service)
    user = _user("Staff")
    route = documents.submit_signature if action == "submit" else documents.decline_signature

    with pytest.raises(HTTPException) as info:
        await route(signature_id=str(uuid4()), request=SimpleNamespace(), current_user=user, db=None)

    assert info.value.status_code == 404 and seen == [user.id]
