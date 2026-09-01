import os
import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.services.adapters.base import BaseAdapter

class CloudbedsAdapter(BaseAdapter):
    
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

        try:
            page_number = 1
            all_reservations = []
            fetch_more = True

            while fetch_more and page_number <= 5:
                url = f"{self._get_base_url()}/getReservations"
                params = {
                    "startDate": from_date,
                    "endDate": to_date,
                    "pageSize": 100,
                    "pageNumber": page_number
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "X-Property-Id": str(property_id)
                }
                
                async with httpx.AsyncClient() as client:
                    res = await client.get(url, params=params, headers=headers, timeout=15.0)

                if res.status_code != 200:
                    raise Exception(f"Failed to fetch Cloudbeds reservations: {res.reason_phrase}")

                json_data = res.json()
                reservations = json_data.get("data", [])

                if not reservations:
                    break

                for resv in reservations:
                    check_in = datetime.fromisoformat(resv["startDate"])
                    check_out = datetime.fromisoformat(resv["endDate"])
                    num_nights = (check_out - check_in).days or 1

                    status = resv.get("status", "confirmed")
                    if status not in ["confirmed", "checked_in", "checked_out", "cancelled", "no_show"]:
                        status = "confirmed"

                    all_reservations.append({
                        "external_id": str(resv.get("reservationID")),
                        "status": status,
                        "guest_name": resv.get("guestName", "Unknown Guest"),
                        "guest_email": resv.get("guestEmail"),
                        "guest_phone": resv.get("guestPhone"),
                        "room_number": str(resv.get("roomID", "N/A")),
                        "room_type": resv.get("roomTypeName", "Standard"),
                        "check_in_date": check_in,
                        "check_out_date": check_out,
                        "num_nights": num_nights,
                        "num_adults": resv.get("adults", 1),
                        "num_children": resv.get("children", 0),
                        "total_amount": float(resv.get("grandTotal") or 0.0),
                        "currency": resv.get("currency", "USD"),
                        "booking_source": resv.get("channelName", "Direct"),
                        "special_requests": resv.get("specialRequests"),
                        "booked_at": datetime.fromisoformat(resv["dateCreated"].replace("Z", "+00:00")) if "dateCreated" in resv else datetime.now()
                    })

                if len(reservations) < 100:
                    fetch_more = False
                else:
                    page_number += 1

            return all_reservations
        except Exception as e:
            print(f"Error fetching Cloudbeds reservations: {e}")
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
            print(f"Error fetching Cloudbeds availability: {e}")
            raise e
