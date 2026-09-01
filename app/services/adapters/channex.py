import os
import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.services.adapters.base import BaseAdapter

class ChannexAdapter(BaseAdapter):
    
    def _get_base_url(self) -> str:
        return os.getenv("CHANNEX_BASE_URL", "https://staging.channex.io/api/v1")

    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        api_key = credentials.get("api_key")
        if not api_key:
            return {"success": False, "message": "API key is required."}

        # Mock bypass for testing
        if api_key == "mock_channex_key" or api_key.startswith("mock"):
            return {"success": True, "message": "Connected successfully (Mock). Found 2 properties."}

        try:
            url = f"{self._get_base_url()}/properties"
            headers = {
                "user-api-key": api_key,
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=10.0)

            if res.status_code in [401, 403]:
                return {"success": False, "message": "Invalid API key. Please check and try again."}
            elif res.status_code == 429:
                return {"success": False, "message": "Rate limit hit. Please try again in a minute."}
            elif res.status_code != 200:
                return {"success": False, "message": f"Provider API error: {res.reason_phrase}"}

            data = res.json()
            count = len(data.get("data", []))
            return {"success": True, "message": f"Connected successfully. Found {count} property/properties."}

        except Exception as e:
            return {"success": False, "message": f"Provider API is currently unavailable: {str(e)}"}

    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_key = credentials.get("api_key")

        # Mock bypass
        if api_key == "mock_channex_key" or (api_key and api_key.startswith("mock")):
            return [
                {
                    "external_id": "chx-res-9901",
                    "status": "confirmed",
                    "guest_name": "John Doe",
                    "guest_email": "john.doe@example.com",
                    "guest_phone": "+1-555-0199",
                    "room_number": "101",
                    "room_type": "King Room",
                    "check_in_date": datetime.fromisoformat(from_date),
                    "check_out_date": datetime.fromisoformat(to_date),
                    "num_nights": 2,
                    "num_adults": 2,
                    "num_children": 0,
                    "total_amount": 350.0,
                    "currency": "USD",
                    "booking_source": "Booking.com",
                    "special_requests": "Late check-in requested.",
                    "booked_at": datetime.now()
                }
            ]

        try:
            url = f"{self._get_base_url()}/bookings"
            params = {
                "filter[property_id]": property_id,
                "filter[date_from]": from_date,
                "filter[date_to]": to_date
            }
            headers = {"user-api-key": api_key}
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params=params, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch Channex reservations: {res.reason_phrase}")

            data = res.json()
            bookings = data.get("data", [])
            unified = []

            for booking in bookings:
                rooms = booking.get("rooms", [])
                room = rooms[0] if rooms else {}
                days = room.get("days", [])
                total_amount = sum(float(day.get("price", 0)) for day in days)

                check_in = datetime.fromisoformat(booking["arrival_date"])
                check_out = datetime.fromisoformat(booking["departure_date"])
                num_nights = (check_out - check_in).days or 1

                status = "cancelled" if booking.get("status") == "cancelled" else "confirmed"

                unified.append({
                    "external_id": str(booking.get("booking_id") or booking.get("id")),
                    "status": status,
                    "guest_name": booking.get("guest", {}).get("name", "Unknown Guest"),
                    "guest_email": booking.get("guest", {}).get("mail"),
                    "guest_phone": booking.get("guest", {}).get("phone"),
                    "room_number": str(room.get("id", "N/A")),
                    "room_type": room.get("room_type_name", "Standard"),
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": booking.get("adults", 1),
                    "num_children": booking.get("children", 0),
                    "total_amount": total_amount,
                    "currency": booking.get("currency", "USD"),
                    "booking_source": booking.get("ota_name", "Direct"),
                    "special_requests": booking.get("special_requests"),
                    "booked_at": datetime.fromisoformat(booking["inserted_at"].replace("Z", "+00:00")) if "inserted_at" in booking else datetime.now()
                })

            return unified
        except Exception as e:
            print(f"Error fetching from Channex API: {e}")
            raise e

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_key = credentials.get("api_key")

        # Mock bypass
        if api_key == "mock_channex_key" or (api_key and api_key.startswith("mock")):
            return [
                {
                    "room_id": "room-101",
                    "date": from_date,
                    "is_available": True,
                    "rate": 175.0
                }
            ]

        try:
            url = f"{self._get_base_url()}/restrictions"
            params = {
                "property_id": property_id,
                "date_from": from_date,
                "date_to": to_date
            }
            headers = {"user-api-key": api_key}
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params=params, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch Channex restrictions: {res.reason_phrase}")

            data = res.json()
            restrictions = data.get("data", [])
            unified = []

            for item in restrictions:
                unified.append({
                    "room_id": str(item.get("room_type_id") or item.get("id")),
                    "date": item.get("date"),
                    "is_available": not item.get("stop_sell", False),
                    "rate": float(item.get("rate") or 0.0)
                })

            return unified
        except Exception as e:
            print(f"Error fetching availability from Channex: {e}")
            raise e
