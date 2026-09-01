import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.utils.crypto import decrypt

router = APIRouter()

@router.post("/webhooks/little-hotelier")
async def little_hotelier_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lh_smx_token: str = Header(None),
    x_smx_token: str = Header(None),
    authorization: str = Header(None)
):
    token = x_lh_smx_token or x_smx_token
    if not token and authorization:
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. SMX Token header is missing."
        )
        
    # Scan integrations to find matching active Little Hotelier integration
    integrations_query = text("SELECT * FROM integrations WHERE provider_name = 'little_hotelier' AND connection_status = 'active'")
    integrations = (await db.execute(integrations_query)).fetchall()
    
    matching_integration = None
    for integration in integrations:
        try:
            creds_raw = decrypt(integration.credentials_json)
            creds = json.loads(creds_raw)
            if creds.get("smx_token") == token:
                matching_integration = integration
                break
        except Exception:
            continue
            
    if not matching_integration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. No matching active integration found for token."
        )
        
    # Parse payload
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
        
    rq = body.get("OTA_HotelResNotifRQ")
    if not rq:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload structure. OTA_HotelResNotifRQ missing."
        )
        
    hotel_reservations = rq.get("HotelReservations", [])
    hotel_reservation = hotel_reservations[0] if hotel_reservations else {}
    unique_id = hotel_reservation.get("UniqueID", {})
    external_id = str(unique_id.get("ID") or f"lh-webhook-{int(datetime.now().timestamp())}")
    
    res_status = hotel_reservation.get("ResStatus", "New")
    status_str = "cancelled" if res_status.lower() == "cancelled" else "confirmed"
    
    room_stays = hotel_reservation.get("RoomStays", [])
    room_stay = room_stays[0] if room_stays else {}
    room_rates = room_stay.get("RoomRates", [])
    room_rate = room_rates[0] if room_rates else {}
    guest_counts = room_stay.get("GuestCounts", [])
    
    num_adults = 1
    num_children = 0
    for g in guest_counts:
        if g.get("AgeQualifyingCode") == "10":
            num_adults = g.get("Count", 1)
        elif g.get("AgeQualifyingCode") == "8":
            num_children = g.get("Count", 0)
            
    time_span = room_stay.get("TimeSpan", {})
    check_in_date = time_span.get("Start") or datetime.now().strftime("%Y-%m-%d")
    check_out_date = time_span.get("End") or datetime.now().strftime("%Y-%m-%d")
    
    try:
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d")
        num_nights = (check_out - check_in).days or 1
    except Exception:
        check_in = datetime.now()
        check_out = datetime.now()
        num_nights = 1
    
    total_amount = float(room_rate.get("Total", {}).get("AmountBeforeTax") or 120.0)
    currency = room_rate.get("Total", {}).get("CurrencyCode", "USD")
    
    res_guests = hotel_reservation.get("ResGuests", [])
    res_guest = res_guests[0] if res_guests else {}
    profiles = res_guest.get("Profiles", [])
    profile_item = profiles[0].get("Profile", {}) if profiles else {}
    customer = profile_item.get("Customer", {})
    person_name = customer.get("PersonName", {})
    
    guest_name = f"{person_name.get('GivenName', '')} {person_name.get('Surname', 'Unknown Guest')}".strip()
    if not guest_name:
        guest_name = "Unknown Guest"
        
    guest_email = customer.get("Email")
    guest_phone = customer.get("Telephone")
    
    room_types = room_stay.get("RoomTypes", [])
    room_type_item = room_types[0] if room_types else {}
    room_type = room_type_item.get("RoomType", "Standard Room")
    room_number = room_type_item.get("RoomID", "N/A")
    
    # Save to database
    save_query = text("""
        INSERT INTO reservations (
            tenant_id, property_id, integration_id, external_id,
            status, guest_name, guest_email, guest_phone,
            room_number, room_type, check_in_date, check_out_date,
            num_nights, num_adults, num_children,
            total_amount, currency, booking_source, special_requests,
            booked_at, synced_at
        ) VALUES (
            :tenant_id, :property_id, :integration_id, :external_id,
            :status, :guest_name, :guest_email, :guest_phone,
            :room_number, :room_type, :check_in_date, :check_out_date,
            :num_nights, :num_adults, :num_children,
            :total_amount, :currency, 'Little Hotelier Webhook', :special_requests,
            NOW(), NOW()
        )
        ON CONFLICT (integration_id, external_id)
        DO UPDATE SET
            status = EXCLUDED.status,
            room_number = EXCLUDED.room_number,
            check_in_date = EXCLUDED.check_in_date,
            check_out_date = EXCLUDED.check_out_date,
            total_amount = EXCLUDED.total_amount,
            synced_at = NOW()
    """)
    
    await db.execute(save_query, {
        "tenant_id": matching_integration.tenant_id,
        "property_id": matching_integration.property_id,
        "integration_id": matching_integration.id,
        "external_id": external_id,
        "status": status_str,
        "guest_name": guest_name,
        "guest_email": guest_email,
        "guest_phone": guest_phone,
        "room_number": room_number,
        "room_type": room_type,
        "check_in_date": check_in,
        "check_out_date": check_out,
        "num_nights": num_nights,
        "num_adults": num_adults,
        "num_children": num_children,
        "total_amount": total_amount,
        "currency": currency,
        "special_requests": hotel_reservation.get("Comments")
    })
    
    # Update last sync time
    update_sync_query = text("UPDATE integrations SET last_sync_at = NOW() WHERE id = :id")
    await db.execute(update_sync_query, {"id": matching_integration.id})
    await db.commit()
    
    # Return standard response payload
    return {
        "OTA_HotelResNotifRS": {
            "Success": {},
            "UniqueID": {
                "ID": external_id
            },
            "TimeStamp": datetime.now().isoformat()
        }
    }
