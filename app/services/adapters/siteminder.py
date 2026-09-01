import os
import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.services.adapters.base import BaseAdapter

class SiteMinderAdapter(BaseAdapter):
    
    def _get_base_url(self) -> str:
        return os.getenv("SITEMINDER_BASE_URL", "https://tpi-channel-api.preprod.smchannelsplus.com")

    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        api_id = credentials.get("api_id")
        api_key = credentials.get("api_key")

        if not api_id or not api_key:
            return {"success": False, "message": "Both API ID and API Key are required."}

        if api_id == "mock_siteminder_id" or api_id.startswith("mock"):
            return {"success": True, "message": "Connected successfully (Mock). Found 1 property."}

        try:
            url = f"{self._get_base_url()}/properties"
            headers = {
                "x-sm-api-id": api_id,
                "x-sm-api-key": api_key,
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=10.0)

            if res.status_code in [401, 403]:
                return {"success": False, "message": "Invalid SiteMinder credentials."}
            elif res.status_code != 200:
                return {"success": False, "message": f"SiteMinder API error: {res.reason_phrase}"}

            json_data = res.json()
            count = len(json_data.get("properties", []))
            return {"success": True, "message": f"Connected successfully. Found {count} property/properties."}

        except Exception as e:
            return {"success": False, "message": f"SiteMinder API is currently unavailable: {str(e)}"}

    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_id = credentials.get("api_id")
        api_key = credentials.get("api_key")

        if api_id == "mock_siteminder_id" or (api_id and api_id.startswith("mock")):
            return [
                {
                    "external_id": "sm-res-5503",
                    "status": "confirmed",
                    "guest_name": "David Miller",
                    "guest_email": "david.miller@example.com",
                    "guest_phone": "+1-555-0811",
                    "room_number": "404",
                    "room_type": "Penthouse Suite",
                    "check_in_date": datetime.fromisoformat(from_date),
                    "check_out_date": datetime.fromisoformat(to_date),
                    "num_nights": 4,
                    "num_adults": 2,
                    "num_children": 1,
                    "total_amount": 1200.0,
                    "currency": "USD",
                    "booking_source": "SiteMinder GDS",
                    "special_requests": "Champagne on arrival.",
                    "booked_at": datetime.now()
                }
            ]

        try:
            url = f"{self._get_base_url()}/reservations"
            params = {
                "check_in_from": from_date,
                "check_in_to": to_date
            }
            headers = {
                "x-sm-api-id": api_id,
                "x-sm-api-key": api_key
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params=params, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch SiteMinder reservations: {res.reason_phrase}")

            json_data = res.json()
            reservations = json_data.get("reservations", [])
            unified = []

            for resv in reservations:
                check_in = datetime.fromisoformat(resv["check_in_date"])
                check_out = datetime.fromisoformat(resv["check_out_date"])
                num_nights = (check_out - check_in).days or 1

                unified.append({
                    "external_id": str(resv.get("id")),
                    "status": "cancelled" if resv.get("status") == "cancelled" else "confirmed",
                    "guest_name": resv.get("primary_guest_name", "Unknown Guest"),
                    "guest_email": resv.get("primary_guest_email"),
                    "guest_phone": resv.get("primary_guest_phone"),
                    "room_number": str(resv.get("room_number", "N/A")),
                    "room_type": resv.get("room_type_name", "Standard"),
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": resv.get("adults", 1),
                    "num_children": resv.get("children", 0),
                    "total_amount": float(resv.get("total_rate") or 0.0),
                    "currency": resv.get("currency", "USD"),
                    "booking_source": resv.get("source_channel", "SiteMinder"),
                    "special_requests": resv.get("comments"),
                    "booked_at": datetime.fromisoformat(resv["created_at"].replace("Z", "+00:00")) if "created_at" in resv else datetime.now()
                })

            return unified
        except Exception as e:
            print(f"Error fetching SiteMinder reservations: {e}")
            raise e

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        api_id = credentials.get("api_id")
        api_key = credentials.get("api_key")

        if api_id == "mock_siteminder_id" or (api_id and api_id.startswith("mock")):
            return [
                {
                    "room_id": "room-404",
                    "date": from_date,
                    "is_available": True,
                    "rate": 300.0
                }
            ]

        try:
            url = f"{self._get_base_url()}/properties/{property_id}"
            headers = {
                "x-sm-api-id": api_id,
                "x-sm-api-key": api_key
            }
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch SiteMinder availability: {res.reason_phrase}")

            json_data = res.json()
            availability = json_data.get("availability", [])
            unified = []

            for item in availability:
                unified.append({
                    "room_id": str(item.get("room_id")),
                    "date": item.get("date"),
                    "is_available": int(item.get("available_count") or 0) > 0,
                    "rate": float(item.get("price") or 0.0)
                })

            return unified
        except Exception as e:
            print(f"Error fetching SiteMinder availability: {e}")
            raise e
