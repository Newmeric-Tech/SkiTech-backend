"""
Geofence access scoping - app/services/geofence_scope.py

Who may see or change a property's punch location (geofence):
- Super Admin, Tenant Admin, Co Admin change it directly
  (GEOFENCE_ADMIN_ROLES); a Co Admin with an assigned property only that one.
- A Manager only requests a change, for the property assigned to them
  (JWT property_id = users.property_id), and an admin approves it.
- Everyone is limited to properties of their own tenant.

Out-of-scope properties behave as missing (PropertyNotInScope -> 404), so a
caller can't tell another tenant's property ids from unknown ones.

The JWT role can be up to one access-token lifetime old, so changes that
need an admin also check the role stored now (still_geofence_admin): a
demoted or deactivated admin can't keep approving with an old token.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Property, Role, User

GEOFENCE_ADMIN_ROLES = ("Super Admin", "Tenant Admin", "Co Admin")


class PropertyNotInScope(LookupError):
    """The property doesn't exist, is deleted, or is outside the caller's scope."""


def _as_uuid(value) -> Optional[UUID]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def assigned_property(user: dict) -> Optional[UUID]:
    """The one property a non-tenant-wide caller is limited to, else None
    (Tenant Admin / Super Admin, or a Co Admin without a scoped property)."""
    if user.get("role") in ("Tenant Admin", "Super Admin"):
        return None
    return _as_uuid(user.get("property_id"))


def caller_tenant(user: dict) -> Optional[UUID]:
    return _as_uuid(user.get("tenant_id"))


async def property_in_scope(db: AsyncSession, property_id, user: dict) -> UUID:
    """The property's id if the caller may work with it, else PropertyNotInScope."""
    prop_id = _as_uuid(property_id)
    tenant_id = caller_tenant(user)
    if prop_id is None or tenant_id is None:
        raise PropertyNotInScope()

    role = user.get("role")
    limited_to = assigned_property(user)
    if role in ("Manager", "Staff") and limited_to is None:
        raise PropertyNotInScope()  # no assigned property: nothing in scope
    if limited_to is not None and limited_to != prop_id:
        raise PropertyNotInScope()

    found = (await db.execute(
        select(Property.id).where(
            Property.id == prop_id,
            Property.tenant_id == tenant_id,
            Property.deleted_at == None,
        )
    )).scalar_one_or_none()
    if found is None:
        raise PropertyNotInScope()
    return prop_id


async def current_role(db: AsyncSession, user: dict) -> Optional[str]:
    """The caller's role as stored now; None if the account is gone or inactive."""
    user_id = _as_uuid(user.get("user_id"))
    if user_id is None:
        return None
    return (await db.execute(
        select(Role.name).join(User, User.role_id == Role.id).where(
            User.id == user_id,
            User.is_active == True,
            User.deleted_at == None,
        )
    )).scalar_one_or_none()


async def still_geofence_admin(db: AsyncSession, user: dict) -> bool:
    return await current_role(db, user) in GEOFENCE_ADMIN_ROLES
