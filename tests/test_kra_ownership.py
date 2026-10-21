"""
KRA update/delete (daily, weekly, monthly, quarterly): allowed for the KRA's
own user or a Manager/Tenant Admin/Co Admin/Super Admin; anyone else gets
403 and nothing changes.

Route functions are called directly with fake services; nothing touches a
database.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import kra

TENANT = uuid4()
OWNER = uuid4()
PERIODS = ["daily", "weekly", "monthly", "quarterly"]


class Db:
    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


@pytest.fixture
def changes(monkeypatch):
    log = []

    def make_service(period):
        class Service:
            def __init__(self, db):
                pass

        async def get_by_id(self, kra_id, tenant_id):
            return SimpleNamespace(id=kra_id, tenant_id=tenant_id, user_id=OWNER)

        async def update(self, record, data):
            log.append(("update", period, record.id))
            return record

        async def delete(self, record):
            log.append(("delete", period, record.id))

        setattr(Service, f"get_{period}_kra_by_id", get_by_id)
        setattr(Service, f"update_{period}_kra", update)
        setattr(Service, f"delete_{period}_kra", delete)
        return Service

    for period in PERIODS:
        cap = period.capitalize()
        monkeypatch.setattr(kra, f"{cap}KRAService", make_service(period))
        monkeypatch.setattr(kra, f"{cap}KRAResponse", SimpleNamespace(from_orm=lambda r: r))
    return log


def _ctx(role, user_id=None):
    return {"tenant_id": TENANT, "user_id": user_id or uuid4(), "role": role}


async def _call(action, period, ctx):
    fn = getattr(kra, f"{action}_{period}_kra")
    kwargs = dict(kra_id=uuid4(), db=Db(), user_context=ctx)
    if action == "update":
        kwargs["update_data"] = SimpleNamespace()
    return await fn(**kwargs)


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("action", ["update", "delete"])
async def test_staff_cannot_change_someone_elses_kra(changes, period, action):
    with pytest.raises(HTTPException) as info:
        await _call(action, period, _ctx("Staff"))

    assert info.value.status_code == 403
    assert changes == []


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("action", ["update", "delete"])
async def test_owner_can_change_their_own_kra(changes, period, action):
    await _call(action, period, _ctx("Staff", user_id=OWNER))

    assert [(a, p) for a, p, _ in changes] == [(action, period)]


@pytest.mark.parametrize("role", ["Manager", "Tenant Admin", "Co Admin", "Super Admin"])
@pytest.mark.parametrize("action", ["update", "delete"])
async def test_managers_and_admins_can_change_anyones_kra(changes, role, action):
    for period in PERIODS:
        await _call(action, period, _ctx(role))

    assert [(a, p) for a, p, _ in changes] == [(action, p) for p in PERIODS]
