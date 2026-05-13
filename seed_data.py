"""
seed_data.py — Safe, idempotent seed script for SkiTech.

What it seeds:
  1. Roles              — Super Admin, Tenant Admin, Manager, Staff
  2. Subscription Plans — Starter, Professional, Enterprise
  3. Sample Bookings    — 6 months of revenue data (per existing property + room)

What it NEVER touches:
  - Tenants, Users, Properties, Employees, Departments, or any
    operational data already in the database.

Safe to run multiple times. Skips anything that already exists.

Usage:
    cd skitech_backend
    python seed_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.models import Booking, Property, Role, Room, SubscriptionPlan, Tenant, TenantSubscription, User

# ── Connection ─────────────────────────────────────────────────────────────────

connect_args = {}
if "neon.tech" in settings.DATABASE_URL or settings.is_production:
    connect_args = {"ssl": "require", "server_settings": {"application_name": "skitech-seed"}}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# ── Seed definitions ───────────────────────────────────────────────────────────

ROLES = [
    {"name": "Super Admin",  "role_level": 0, "description": "System administrator with full access"},
    {"name": "Tenant Admin", "role_level": 1, "description": "Tenant administrator — manages all properties"},
    {"name": "Manager",      "role_level": 2, "description": "Property/department manager"},
    {"name": "Staff",        "role_level": 3, "description": "Regular staff member"},
]

SUBSCRIPTION_PLANS = [
    {
        # Tier 1 — free entry plan, core monitoring only
        "name": "Starter",
        "price": Decimal("0.00"),
        "max_properties": 1,
        "max_users": 10,
        "features": {
            "reports":              True,
            "kra":                  True,
            "sop":                  True,
            "attendance":           False,
            "vendor_management":    False,
            "inventory":            False,
            "governance":           False,
            "employee_scheduling":  False,
            "chat":                 False,
            "employee_ranking":     False,
            "master_log":           False,
        },
    },
    {
        # Tier 2 — operational plan, core + attendance & vendors, no inventory
        "name": "Enterprise",
        "price": Decimal("49.00"),
        "max_properties": 3,
        "max_users": 50,
        "features": {
            "reports":              True,
            "kra":                  True,
            "sop":                  True,
            "attendance":           True,
            "vendor_management":    True,
            "inventory":            False,
            "governance":           False,
            "employee_scheduling":  False,
            "chat":                 False,
            "employee_ranking":     False,
            "master_log":           False,
        },
    },
    {
        # Tier 3 — full-feature plan, everything current + all upcoming modules
        "name": "Professional",
        "price": Decimal("99.00"),
        "max_properties": 10,
        "max_users": 200,
        "features": {
            "reports":              True,
            "kra":                  True,
            "sop":                  True,
            "attendance":           True,
            "vendor_management":    True,
            "inventory":            True,
            "governance":           True,
            "employee_scheduling":  True,
            "chat":                 True,
            "employee_ranking":     True,
            "master_log":           True,
        },
    },
]

# Names that should NOT exist — cleaned up on each run
OBSOLETE_PLAN_NAMES = ["Free"]

# ── Seed functions ─────────────────────────────────────────────────────────────

async def seed_roles(session: AsyncSession) -> None:
    print("\n── Roles ─────────────────────────────────────────────")
    for r in ROLES:
        existing = (await session.execute(select(Role).where(Role.name == r["name"]))).scalar_one_or_none()
        if existing:
            print(f"  skip  '{r['name']}' (already exists)")
            continue
        session.add(Role(**r))
        print(f"  added '{r['name']}'")
    await session.commit()


async def seed_subscription_plans(session: AsyncSession) -> None:
    """Upsert canonical plans and remove any obsolete ones."""
    print("\n── Subscription Plans ────────────────────────────────")

    # Remove obsolete plans (no active subscriptions guard needed — seed env only)
    for old_name in OBSOLETE_PLAN_NAMES:
        old = (await session.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == old_name))).scalar_one_or_none()
        if old:
            await session.delete(old)
            print(f"  removed obsolete plan '{old_name}'")

    for p in SUBSCRIPTION_PLANS:
        existing = (
            await session.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == p["name"]))
        ).scalar_one_or_none()
        if existing:
            existing.price = p["price"]
            existing.max_properties = p["max_properties"]
            existing.max_users = p["max_users"]
            existing.features = p["features"]
            print(f"  updated '{p['name']}' (features refreshed)")
        else:
            session.add(SubscriptionPlan(**p))
            print(f"  added   '{p['name']}' @ Rs{p['price']}")
    await session.commit()


ROOM_TYPES = ["Standard", "Deluxe", "Suite", "Executive", "Standard"]
ROOM_PRICES = {"Standard": 2500, "Deluxe": 4500, "Suite": 8000, "Executive": 6000}

GUEST_NAMES = [
    "Arjun Mehta", "Priya Sharma", "Rahul Gupta", "Neha Patel",
    "Vikram Singh", "Ananya Iyer", "Rohan Verma", "Sneha Nair",
    "Karan Malhotra", "Divya Reddy",
]


async def _ensure_rooms(session: AsyncSession, prop: Property) -> list:
    """Auto-create Room records from num_rooms + room_number_start if the table is empty."""
    existing = (
        await session.execute(
            select(Room).where(Room.property_id == prop.id, Room.deleted_at == None)
        )
    ).scalars().all()

    if existing:
        return existing

    if not prop.num_rooms or prop.num_rooms <= 0:
        return []

    start = prop.room_number_start if prop.room_number_start else 101
    new_rooms = []
    for i in range(prop.num_rooms):
        room_num = str(start + i)
        room_type = ROOM_TYPES[i % len(ROOM_TYPES)]
        price = ROOM_PRICES.get(room_type, 2500)
        room = Room(
            tenant_id=prop.tenant_id,
            property_id=prop.id,
            room_number=room_num,
            room_type=room_type,
            price_per_night=Decimal(str(price)),
            status="available",
        )
        session.add(room)
        new_rooms.append(room)

    await session.commit()
    # Refresh to get IDs
    for r in new_rooms:
        await session.refresh(r)
    print(f"    auto-created {len(new_rooms)} rooms (#{start}–#{start + prop.num_rooms - 1})")
    return new_rooms


async def seed_sample_bookings(session: AsyncSession) -> None:
    """
    For each property:
      1. Auto-create Room records if the rooms table is empty for that property
         (uses num_rooms + room_number_start from the property record)
      2. Insert 3–6 completed bookings per month for the last 6 months
         (skipped if any bookings already exist for that property)
    """
    print("\n── Sample Bookings (revenue seed) ───────────────────")

    tenants = (await session.execute(select(Tenant).where(Tenant.is_active == True))).scalars().all()
    if not tenants:
        print("  skip — no tenants found")
        return

    now = datetime.now(timezone.utc)
    random.seed(42)

    for tenant in tenants:
        creator = (
            await session.execute(
                select(User).where(User.tenant_id == tenant.id, User.is_active == True).limit(1)
            )
        ).scalar_one_or_none()

        properties = (
            await session.execute(
                select(Property).where(
                    Property.tenant_id == tenant.id,
                    Property.deleted_at == None,
                    Property.is_active == True,
                )
            )
        ).scalars().all()

        for prop in properties:
            existing_bookings = (
                await session.execute(
                    select(func.count(Booking.id)).where(Booking.property_id == prop.id)
                )
            ).scalar() or 0
            if existing_bookings > 0:
                print(f"  skip  '{prop.name}' (already has {existing_bookings} bookings)")
                continue

            rooms = await _ensure_rooms(session, prop)
            if not rooms:
                print(f"  skip  '{prop.name}' (num_rooms not set — set it in the property first)")
                continue

            added = 0
            for months_back in range(5, -1, -1):
                base_date = now - timedelta(days=months_back * 30)
                for _ in range(random.randint(3, 6)):
                    room = random.choice(rooms)
                    check_in = base_date - timedelta(days=random.randint(0, 20))
                    nights = random.randint(1, 5)
                    check_out = check_in + timedelta(days=nights)
                    price_per_night = float(room.price_per_night or 2500)
                    total = Decimal(str(round(price_per_night * nights, 2)))
                    session.add(
                        Booking(
                            tenant_id=tenant.id,
                            property_id=prop.id,
                            room_id=room.id,
                            created_by=creator.id if creator else None,
                            customer_name=random.choice(GUEST_NAMES),
                            customer_phone=f"+91-{random.randint(7000000000, 9999999999)}",
                            check_in=check_in.replace(tzinfo=None),
                            check_out=check_out.replace(tzinfo=None),
                            total_amount=total,
                            status="completed",
                        )
                    )
                    added += 1

            await session.commit()
            print(f"  added {added} bookings for '{prop.name}'")


async def seed_tenant_subscriptions(session: AsyncSession) -> None:
    """Ensure every tenant has an active Professional subscription.
    If the tenant already has an active sub, update it to point to Professional.
    """
    print("\n── Tenant Subscriptions ──────────────────────────────")

    plan = (
        await session.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == "Professional"))
    ).scalar_one_or_none()
    if not plan:
        print("  skip — Professional plan not found (run seed first)")
        return

    tenants = (await session.execute(select(Tenant).where(Tenant.deleted_at == None))).scalars().all()
    if not tenants:
        print("  skip — no tenants found")
        return

    for tenant in tenants:
        existing_sub = (
            await session.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == tenant.id,
                    TenantSubscription.status == "active",
                )
            )
        ).scalar_one_or_none()

        if existing_sub:
            if existing_sub.plan_id == plan.id:
                print(f"  ok    '{tenant.business_name}' — already on Professional")
            else:
                existing_sub.plan_id = plan.id
                print(f"  updated '{tenant.business_name}' → Professional")
            continue

        sub = TenantSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            start_date=datetime.utcnow(),
            status="active",
        )
        session.add(sub)
        print(f"  assigned Professional → '{tenant.business_name}'")

    await session.commit()


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("SkiTech seed_data.py — starting (safe / idempotent)")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")   # hide credentials

    async with AsyncSessionLocal() as session:
        await seed_roles(session)
        await seed_subscription_plans(session)
        await seed_tenant_subscriptions(session)
        await seed_sample_bookings(session)

    await engine.dispose()
    print("\nDone. Existing tenants, users, and properties were not modified.")


if __name__ == "__main__":
    asyncio.run(main())
