import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.services.adapters.base import BaseAdapter

class LittleHotelierAdapter(BaseAdapter):
    
    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        smx_token = credentials.get("smx_token")
        if not smx_token:
            return {"success": False, "message": "SMX Token is required."}

        if smx_token == "mock_lh_token" or smx_token.startswith("mock"):
            return {"success": True, "message": "Connected successfully (Mock). SMX webhook registered."}

        try:
            # Little Hotelier uses SiteMinder SMX API pull gateway to verify tokens.
            url = 'https://smx.siteminder.com/smx/reservations?limit=1'
            headers = {"Authorization": f"Bearer {smx_token}"}
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=10.0)

            if res.status_code in [401, 403]:
                return {"success": False, "message": "Invalid SMX Token."}
            elif res.status_code != 200:
                return {"success": False, "message": f"LH Gateway error: {res.reason_phrase}"}

            return {"success": True, "message": "Connected successfully. SMX Token is active."}
        except Exception as e:
            return {"success": False, "message": f"Little Hotelier API is currently unavailable: {str(e)}"}

    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        smx_token = credentials.get("smx_token")

        if smx_token == "mock_lh_token" or (smx_token and smx_token.startswith("mock")):
            return [
                {
                    "external_id": "lh-res-6604",
                    "status": "confirmed",
                    "guest_name": "Sarah Williams",
                    "guest_email": "sarah.w@example.com",
                    "guest_phone": "+1-555-0944",
                    "room_number": "505",
                    "room_type": "Cottage Suite",
                    "check_in_date": datetime.fromisoformat(from_date),
                    "check_out_date": datetime.fromisoformat(to_date),
                    "num_nights": 1,
                    "num_adults": 2,
                    "num_children": 0,
                    "total_amount": 195.0,
                    "currency": "USD",
                    "booking_source": "Direct (LH)",
                    "special_requests": None,
                    "booked_at": datetime.now()
                }
            ]

        try:
            url = f"https://smx.siteminder.com/smx/reservations"
            params = {
                "startDate": from_date,
                "endDate": to_date
            }
            headers = {"Authorization": f"Bearer {smx_token}"}
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params=params, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to pull Little Hotelier reservations: {res.reason_phrase}")

            json_data = res.json()
            reservations = json_data.get("reservations", [])
            unified = []

            for resv in reservations:
                check_in = datetime.fromisoformat(resv["arrival_date"])
                check_out = datetime.fromisoformat(resv["departure_date"])
                num_nights = (check_out - check_in).days or 1

                unified.append({
                    "external_id": str(resv.get("id")),
                    "status": "cancelled" if resv.get("status") == "cancelled" else "confirmed",
                    "guest_name": resv.get("guest_name", "Unknown Guest"),
                    "guest_email": resv.get("guest_email"),
                    "guest_phone": resv.get("guest_phone"),
                    "room_number": str(resv.get("room_name", "N/A")),
                    "room_type": resv.get("room_type", "Standard"),
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": resv.get("adults", 1),
                    "num_children": resv.get("children", 0),
                    "total_amount": float(resv.get("total_price") or 0.0),
                    "currency": resv.get("currency", "USD"),
                    "booking_source": resv.get("source", "Little Hotelier"),
                    "special_requests": resv.get("notes"),
                    "booked_at": datetime.fromisoformat(resv["created_at"].replace("Z", "+00:00")) if "created_at" in resv else datetime.now()
                })

            return unified
        except Exception as e:
            print(f"Error fetching Little Hotelier reservations: {e}")
            raise e

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        smx_token = credentials.get("smx_token")
        if smx_token == "mock_lh_token" or (smx_token and smx_token.startswith("mock")):
            return [
                {
                    "room_id": "room-505",
                    "date": from_date,
                    "is_available": True,
                    "rate": 195.0
                }
            ]
        return []
