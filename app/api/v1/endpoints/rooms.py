"""
Rooms & Bookings Routes - app/api/v1/endpoints/rooms.py

Rooms:
GET    /rooms/{property_id}              → list all rooms
POST   /rooms/{property_id}             → create room
GET    /rooms/detail/{room_id}          → get single room
PUT    /rooms/{room_id}                 → update room
DELETE /rooms/{room_id}                 → delete room

Bookings:
POST   /rooms/{property_id}/bookings          → create booking
GET    /rooms/{property_id}/bookings          → list all bookings
GET    /rooms/bookings/detail/{booking_id}    → get single booking
PUT    /rooms/bookings/{booking_id}           → update booking
PUT    /rooms/bookings/{booking_id}/checkin   → check in
PUT    /rooms/bookings/{booking_id}/checkout  → check out
PUT    /rooms/bookings/{booking_id}/cancel    → cancel booking
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decimal import Decimal

from app.api.dependencies import get_current_user, require_permission, require_roles
from app.core.database import get_db
from app.models.models import Booking, Property, Room
from app.schemas.schemas import (
    BookingCreate, BookingResponse, BookingUpdate,
    RoomCreate, RoomResponse, RoomUpdate,
)

ROOM_TYPES = ["Standard", "Deluxe", "Suite", "Executive"]


class BulkStatusUpdate(BaseModel):
    room_ids: List[str]
    status: str
ROOM_PRICES = {"Standard": Decimal("2500"), "Deluxe": Decimal("4500"), "Suite": Decimal("8000"), "Executive": Decimal("6000")}

router = APIRouter(prefix="/rooms", tags=["Rooms & Bookings"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_room_or_404(
    db: AsyncSession, room_id: UUID, tenant_id: UUID
) -> Room:
    result = await db.execute(
        select(Room).where(
            Room.id == room_id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


async def _get_booking_or_404(
    db: AsyncSession, booking_id: UUID, tenant_id: UUID
) -> Booking:
    result = await db.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.tenant_id == tenant_id,
            Booking.deleted_at == None,
        )
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


# ── Rooms CRUD ────────────────────────────────────────────────────────────────

@router.post("/{property_id}", response_model=RoomResponse, status_code=201)
async def create_room(
    property_id: UUID,
    data: RoomCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Create a new room for a property."""
    tenant_id = UUID(user["tenant_id"])

    # Check duplicate room number in same property (scoped to tenant)
    dup = await db.execute(
        select(Room).where(
            Room.property_id == property_id,
            Room.tenant_id == tenant_id,
            Room.room_number == data.room_number,
            Room.deleted_at == None,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Room number '{data.room_number}' already exists in this property",
        )

    room = Room(
        tenant_id=tenant_id,
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{property_id}", response_model=List[RoomResponse])
async def list_rooms(
    property_id: UUID,
    status: Optional[str] = None,
    room_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all rooms for a property. Optional filters: status, room_type."""
    tenant_id = UUID(user["tenant_id"])

    q = select(Room).where(
        Room.property_id == property_id,
        Room.tenant_id == tenant_id,
        Room.deleted_at == None,
    )
    if status:
        q = q.where(Room.status == status)
    if room_type:
        q = q.where(Room.room_type == room_type)

    result = await db.execute(q)
    return result.scalars().all()


@router.get("/detail/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single room by ID."""
    return await _get_room_or_404(db, room_id, UUID(user["tenant_id"]))


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: UUID,
    data: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Update room details or status."""
    room = await _get_room_or_404(db, room_id, UUID(user["tenant_id"]))
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(room, k, v)
    await db.commit()
    await db.refresh(room)
    return room


@router.delete("/{room_id}")
async def delete_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Soft delete a room."""
    room = await _get_room_or_404(db, room_id, UUID(user["tenant_id"]))
    room.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Room deleted successfully"}


# ── Bulk Status Update ───────────────────────────────────────────────────────

@router.post("/{property_id}/bulk-status")
async def bulk_update_room_status(
    property_id: UUID,
    data: BulkStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Update status of multiple rooms at once."""
    if data.status not in ["available", "occupied", "maintenance"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be available, occupied, or maintenance")

    tenant_id = UUID(user["tenant_id"])
    room_uuids = [UUID(rid) for rid in data.room_ids]

    result = await db.execute(
        select(Room).where(
            Room.id.in_(room_uuids),
            Room.property_id == property_id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
        )
    )
    rooms = result.scalars().all()
    for room in rooms:
        room.status = data.status
    await db.commit()
    return {"updated": len(rooms), "status": data.status}


# ── Regenerate Rooms ──────────────────────────────────────────────────────────

@router.post("/{property_id}/regenerate", response_model=List[RoomResponse])
async def regenerate_rooms(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """
    Delete all existing rooms for this property and recreate them fresh using
    the property's current num_rooms and room_number_start values.

    Blocked if any room has an active booking (booked or checked_in).
    Only Tenant Admin and Super Admin can call this.
    """
    tenant_id = UUID(user["tenant_id"])

    # Load property
    prop_result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.tenant_id == tenant_id,
            Property.deleted_at == None,
        )
    )
    prop = prop_result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if not prop.num_rooms or prop.num_rooms <= 0:
        raise HTTPException(status_code=400, detail="Property has no num_rooms set. Update the property first.")

    # Block if active bookings exist for any room in this property
    active_bookings = (await db.execute(
        select(func.count(Booking.id)).where(
            Booking.property_id == property_id,
            Booking.tenant_id == tenant_id,
            Booking.status.in_(["booked", "checked_in"]),
            Booking.deleted_at == None,
        )
    )).scalar() or 0

    if active_bookings > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot regenerate — {active_bookings} active booking(s) exist. Check out or cancel them first.",
        )

    # Soft-delete all existing rooms for this property
    existing_rooms = (await db.execute(
        select(Room).where(
            Room.property_id == property_id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
        )
    )).scalars().all()

    now = datetime.utcnow()
    for room in existing_rooms:
        room.deleted_at = now

    await db.flush()

    # Recreate rooms from scratch
    start = prop.room_number_start if prop.room_number_start else 101
    new_rooms = []
    for i in range(prop.num_rooms):
        room_type = ROOM_TYPES[i % len(ROOM_TYPES)]
        room = Room(
            tenant_id=tenant_id,
            property_id=property_id,
            room_number=str(start + i),
            room_type=room_type,
            price_per_night=ROOM_PRICES.get(room_type, Decimal("2500")),
            status="available",
        )
        db.add(room)
        new_rooms.append(room)

    await db.commit()
    for r in new_rooms:
        await db.refresh(r)

    return new_rooms


# ── Bookings ──────────────────────────────────────────────────────────────────

@router.post("/{property_id}/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(
    property_id: UUID,
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new booking. Checks room availability before confirming."""
    tenant_id = UUID(user["tenant_id"])

    # Check room exists and belongs to this property
    room_result = await db.execute(
        select(Room).where(
            Room.id == data.room_id,
            Room.property_id == property_id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
        )
    )
    room = room_result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found in this property")

    # Check room is available
    if room.status != "available":
        raise HTTPException(
            status_code=400,
            detail=f"Room is currently '{room.status}' — cannot be booked",
        )

    # Check no overlapping active bookings for this room
    overlap = await db.execute(
        select(Booking).where(
            Booking.room_id == data.room_id,
            Booking.deleted_at == None,
            Booking.status.in_(["booked", "checked_in"]),
            Booking.check_in < data.check_out,
            Booking.check_out > data.check_in,
        )
    )
    if overlap.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Room already has an active booking for the selected dates",
        )

    booking = Booking(
        tenant_id=tenant_id,
        property_id=property_id,
        created_by=UUID(user["user_id"]),
        **data.model_dump(),
    )
    db.add(booking)

    # Mark room as occupied
    room.status = "occupied"

    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{property_id}/bookings", response_model=List[BookingResponse])
async def list_bookings(
    property_id: UUID,
    status: Optional[str] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all bookings for a property."""
    tenant_id = UUID(user["tenant_id"])

    q = select(Booking).where(
        Booking.property_id == property_id,
        Booking.tenant_id == tenant_id,
        Booking.deleted_at == None,
    )
    if status:
        q = q.where(Booking.status == status)

    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/bookings/detail/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single booking by ID."""
    return await _get_booking_or_404(db, booking_id, UUID(user["tenant_id"]))


@router.put("/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: UUID,
    data: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Update booking details."""
    booking = await _get_booking_or_404(db, booking_id, UUID(user["tenant_id"]))

    if booking.status in ["completed", "cancelled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update a '{booking.status}' booking",
        )

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(booking, k, v)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.put("/bookings/{booking_id}/checkin", response_model=BookingResponse)
async def checkin_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Mark a booking as checked in."""
    booking = await _get_booking_or_404(db, booking_id, UUID(user["tenant_id"]))

    if booking.status != "booked":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot check in a '{booking.status}' booking",
        )

    booking.status = "checked_in"
    await db.commit()
    await db.refresh(booking)
    return booking


@router.put("/bookings/{booking_id}/checkout", response_model=BookingResponse)
async def checkout_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Mark a booking as completed and free up the room."""
    tenant_id = UUID(user["tenant_id"])
    booking = await _get_booking_or_404(db, booking_id, tenant_id)

    if booking.status != "checked_in":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot check out a '{booking.status}' booking",
        )

    booking.status = "completed"

    # Free up the room
    room_result = await db.execute(
        select(Room).where(
            Room.id == booking.room_id,
            Room.tenant_id == tenant_id,
        )
    )
    room = room_result.scalar_one_or_none()
    if room:
        room.status = "available"

    await db.commit()
    await db.refresh(booking)
    return booking


@router.put("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Cancel a booking and free up the room."""
    tenant_id = UUID(user["tenant_id"])
    booking = await _get_booking_or_404(db, booking_id, tenant_id)

    if booking.status in ["completed", "cancelled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel a '{booking.status}' booking",
        )

    booking.status = "cancelled"

    # Free up the room
    room_result = await db.execute(
        select(Room).where(
            Room.id == booking.room_id,
            Room.tenant_id == tenant_id,
        )
    )
    room = room_result.scalar_one_or_none()
    if room:
        room.status = "available"

    await db.commit()
    await db.refresh(booking)
    return booking