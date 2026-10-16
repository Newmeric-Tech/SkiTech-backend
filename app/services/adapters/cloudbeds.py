import os
import httpx
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.services.adapters.base import BaseAdapter
from app.utils.safe_errors import safe_error_summary

# Cloudbeds API reference (developers.cloudbeds.com/reference):
#   getReservations                -> get_getreservations-2
#   getReservationsWithRateDetails -> get_getreservationswithratedetails-2
#   getRooms                       -> get_getrooms-2
PAGE_SIZE = 100        # pageSize: "Results page size. Max = 100"
RATE_ID_BATCH = 100    # reservationID is "comma-separated"; no max documented
MAX_ROOM_PAGES = 100   # getRooms documents no page-size max; bound the walk

# Reservation status enum: not_confirmed, confirmed, canceled, checked_in,
# checked_out, no_show. Note "canceled" with one L.
_STATUS_MAP = {
    "not_confirmed": "confirmed",
    "confirmed": "confirmed",
    "canceled": "cancelled",
    "checked_in": "checked_in",
    "checked_out": "checked_out",
    "no_show": "no_show",
}


def _parse_created(value: Optional[str]) -> Optional[datetime]:
    # dateCreated is documented only as format date-time.
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class CloudbedsAdapter(BaseAdapter):

    supports_room_sync = True

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        # transport is injectable so tests can serve stored fixtures
        self._transport = transport

    def _get_base_url(self) -> str:
        return os.getenv("CLOUDBEDS_BASE_URL", "https://hotels.cloudbeds.com/api/v1.2")

    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        api_key = credentials.get("api_key")
        property_id = credentials.get("property_id")
        
        if not api_key or not property_id:
            return {"success": False, "message": "Both API Key (Access Token) and Property ID are required."}

        if api_key == "mock_cloudbeds_key" or api_key.startswith("mock"):
            return {"success": True, "message": "Connected successfully (Mock). Hotel: Cloudbeds Grand Plaza"}

        try:
            url = f"{self._get_base_url()}/getHotelDetails"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "X-Property-Id": str(property_id),
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=10.0)

            if res.status_code in [401, 403]:
                return {"success": False, "message": "Invalid API key or Property ID for Cloudbeds."}
            elif res.status_code != 200:
                return {"success": False, "message": f"Cloudbeds API returned error: {res.reason_phrase}"}

            json_data = res.json()
            if json_data.get("success") and json_data.get("data", {}).get("property_name"):
                name = json_data["data"]["property_name"]
                return {"success": True, "message": f"Connected successfully. Hotel: {name}"}

            return {"success": False, "message": json_data.get("message") or "Failed to authenticate. Verify credentials."}

        except Exception as e:
            return {"success": False, "message": f"Cloudbeds API is currently unavailable: {str(e)}"}

    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id_ignored: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_key = credentials.get("api_key")
        property_id = credentials.get("property_id")

        if api_key == "mock_cloudbeds_key" or (api_key and api_key.startswith("mock")):
            return [
                {
                    "external_id": "cb-res-4402",
                    "status": "confirmed",
                    "guest_name": "Robert Johnson",
                    "guest_email": "robert.j@example.com",
                    "guest_phone": "+1-555-0722",
                    "room_number": "303",
                    "room_type": "Queen Deluxe",
                    "check_in_date": datetime.fromisoformat(from_date),
                    "check_out_date": datetime.fromisoformat(to_date),
                    "num_nights": 2,
                    "num_adults": 2,
                    "num_children": 0,
                    "total_amount": 280.0,
                    "currency": "USD",
                    "booking_source": "Airbnb",
                    "special_requests": "Require early check-in.",
                    "booked_at": datetime.now()
                }
            ]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Property-Id": str(property_id)
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
                # checkInFrom/checkInTo are the documented check-in filters; the
                # previous startDate/endDate are not getReservations parameters.
                # includeAllRooms returns rooms[] (roomID, roomName, roomTypeName);
                # includeGuestsDetails returns guestList (guestEmail, guestPhone).
                reservations = await self._get_pages(client, "/getReservations", headers, {
                    "propertyID": str(property_id),
                    "checkInFrom": from_date,
                    "checkInTo": to_date,
                    "includeAllRooms": "true",
                    "includeGuestsDetails": "true",
                })

                # getReservations has no total or currency; the rate-details
                # endpoint documents total and propertyCurrency per reservation.
                rate_details: Dict[str, Dict[str, Any]] = {}
                ids = [str(r["reservationID"]) for r in reservations]
                for i in range(0, len(ids), RATE_ID_BATCH):
                    for d in await self._get_pages(client, "/getReservationsWithRateDetails", headers, {
                        "propertyID": str(property_id),
                        "reservationID": ",".join(ids[i:i + RATE_ID_BATCH]),
                    }):
                        rate_details[str(d["reservationID"])] = d

            all_reservations = []
            for resv in reservations:
                check_in = datetime.fromisoformat(resv["startDate"])
                check_out = datetime.fromisoformat(resv["endDate"])
                num_nights = (check_out - check_in).days or 1

                # A reservation can hold several rooms; like the other adapters
                # we keep one row per reservation and report the first room.
                rooms = resv.get("rooms") or []
                room = next((r for r in rooms if r.get("roomID")), rooms[0] if rooms else {})

                guests = (resv.get("guestList") or {}).values()
                main_guest = next((g for g in guests if g.get("isMainGuest")), {})

                rates = rate_details.get(str(resv["reservationID"]), {})

                all_reservations.append({
                    "external_id": str(resv.get("reservationID")),
                    "status": _STATUS_MAP.get(resv.get("status"), "confirmed"),
                    "guest_name": resv.get("guestName") or "Unknown Guest",
                    "guest_email": main_guest.get("guestEmail"),
                    "guest_phone": main_guest.get("guestPhone"),
                    "room_number": room.get("roomName") or "N/A",
                    "room_type": room.get("roomTypeName") or "Standard",
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": int(resv.get("adults") or 1),
                    "num_children": int(resv.get("children") or 0),
                    "total_amount": float(rates.get("total") or 0.0),
                    "currency": rates.get("propertyCurrency") or "USD",
                    "booking_source": resv.get("sourceName") or "Direct",
                    "special_requests": None,
                    "booked_at": _parse_created(resv.get("dateCreated")) or datetime.now()
                })

            return all_reservations
        except Exception as e:
            print(f"Error fetching Cloudbeds reservations: {safe_error_summary(e)}")
            raise e

    async def _get_pages(
        self, client: httpx.AsyncClient, path: str, headers: Dict[str, str], params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Walk pageNumber until a short or empty page, or until the
        documented response `total` has been collected."""
        items: List[Dict[str, Any]] = []
        page_number = 1
        while True:
            res = await client.get(
                f"{self._get_base_url()}{path}",
                params={**params, "pageSize": PAGE_SIZE, "pageNumber": page_number},
                headers=headers,
            )
            if res.status_code != 200:
                raise Exception(f"Cloudbeds {path} failed: {res.reason_phrase}")
            json_data = res.json()
            if json_data.get("success") is False:
                raise Exception(f"Cloudbeds {path} failed: {json_data.get('message')}")
            page = json_data.get("data") or []
            items.extend(page)
            total = json_data.get("total")
            if len(page) < PAGE_SIZE or (total is not None and len(items) >= int(total)):
                return items
            page_number += 1

    async def fetch_rooms(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = credentials.get("api_key")
        property_id = credentials.get("property_id")
        # Mock credentials must not create rooms in a real property.
        if api_key == "mock_cloudbeds_key" or (api_key and api_key.startswith("mock")):
            return []

        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Property-Id": str(property_id)
        }
        try:
            # getRooms returns data[] per property with the rooms nested inside,
            # so pages are counted in rooms, not in data items. Rooms are keyed
            # by roomID so a repeated page cannot double-count.
            rooms: Dict[str, Dict[str, Any]] = {}
            async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
                for page_number in range(1, MAX_ROOM_PAGES + 1):
                    res = await client.get(
                        f"{self._get_base_url()}/getRooms",
                        params={"propertyIDs": str(property_id), "pageSize": PAGE_SIZE, "pageNumber": page_number},
                        headers=headers,
                    )
                    if res.status_code != 200:
                        raise Exception(f"Cloudbeds /getRooms failed: {res.reason_phrase}")
                    json_data = res.json()
                    if json_data.get("success") is False:
                        raise Exception(f"Cloudbeds /getRooms failed: {json_data.get('message')}")
                    page = [room for prop in json_data.get("data") or [] for room in prop.get("rooms") or []]
                    for room in page:
                        if room.get("roomID"):
                            rooms[str(room["roomID"])] = room
                    total = json_data.get("total")
                    if len(page) < PAGE_SIZE or (total is not None and len(rooms) >= int(total)):
                        break

            return [
                {
                    "external_id": room_id,
                    "room_number": room.get("roomName"),
                    "room_type": room.get("roomTypeName"),
                }
                for room_id, room in rooms.items()
                if not room.get("isVirtual")
            ]
        except Exception as e:
            print(f"Error fetching Cloudbeds rooms: {safe_error_summary(e)}")
            raise e

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id_ignored: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_key = credentials.get("api_key")
        property_id = credentials.get("property_id")

        if api_key == "mock_cloudbeds_key" or (api_key and api_key.startswith("mock")):
            return [
                {
                    "room_id": "room-303",
                    "date": from_date,
                    "is_available": True,
                    "rate": 140.0
                }
            ]

        try:
            url = f"{self._get_base_url()}/getRatePlans"
            params = {
                "startDate": from_date,
                "endDate": to_date
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "X-Property-Id": str(property_id)
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params=params, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch Cloudbeds rate plans: {res.reason_phrase}")

            json_data = res.json()
            rate_plans = json_data.get("data", [])
            availability_list = []

            for plan in rate_plans:
                rates = plan.get("rates", [])
                for rate in rates:
                    availability_list.append({
                        "room_id": str(plan.get("roomTypeID") or plan.get("id")),
                        "date": rate.get("date"),
                        "is_available": int(rate.get("available") or 0) > 0,
                        "rate": float(rate.get("rate") or 0.0)
                    })

            return availability_list
        except Exception as e:
            print(f"Error fetching Cloudbeds availability: {safe_error_summary(e)}")
            raise e
