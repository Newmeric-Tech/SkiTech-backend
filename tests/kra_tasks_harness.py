"""
Shared helpers for the KRA task tests: real tables on in-memory SQLite behind
an async-shaped wrapper, and row builders that also work on local Postgres.
Never touches the .env database.
"""
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.kra_tasks import KraAssignment, KraDefinition, KraOccurrence
from app.models.models import Property, Role, User

ROLE_NAMES = ("Super Admin", "Tenant Admin", "Co Admin", "Manager", "Staff")


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class SQLiteDB:
    def __init__(self, session):
        self.session = session

    def get_bind(self):
        return self.session.get_bind()

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, obj):
        self.session.add(obj)

    def add_all(self, objs):
        self.session.add_all(objs)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, obj):
        self.session.refresh(obj)


def sqlite_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (Role, User, Property, KraDefinition, KraAssignment, KraOccurrence):
        model.__table__.create(engine)
    return SQLiteDB(Session(engine))


def role_rows():
    return {name: Role(id=uuid4(), name=name, role_level=i) for i, name in enumerate(ROLE_NAMES)}


def user_row(role, tenant_id, property_id=None, is_active=True, first_name="Test", last_name="User"):
    return User(id=uuid4(), email=f"{uuid4().hex}@kra.test", password_hash="x", role_id=role.id,
                tenant_id=tenant_id, property_id=property_id, is_active=is_active, is_verified=True,
                first_name=first_name, last_name=last_name)


def property_row(tenant_id, name=None):
    return Property(id=uuid4(), tenant_id=tenant_id, name=name or uuid4().hex)


def definition_row(tenant_id, property_id, frequency="daily", **kw):
    return KraDefinition(id=uuid4(), tenant_id=tenant_id, property_id=property_id,
                         title=kw.pop("title", "Deposit cash"), frequency=frequency, is_active=kw.pop("is_active", True),
                         **kw)


def assignment_row(definition, assignee_id, start_date, is_active=True):
    return KraAssignment(id=uuid4(), tenant_id=definition.tenant_id, property_id=definition.property_id,
                         definition_id=definition.id, assignee_id=assignee_id, start_date=start_date,
                         is_active=is_active)


