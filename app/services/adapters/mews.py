import os
import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.services.adapters.base import BaseAdapter

class MewsAdapter(BaseAdapter):
    
    def _get_base_url(self) -> str:
        return os.getenv("MEWS_BASE_URL", "https://api.mews-demo.com")

    def _get_client_name(self) -> str:
        return 'TEST Mews Channel Manager Connection'

    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        client_token = credentials.get("client_token")
        access_token = credentials.get("access_token")

        if not client_token or not access_token:
            return {"success": False, "message": "Both Client Token and Access Token are required."}

        if client_token == "mock_client_token" or client_token.startswith("mock"):
            return {"success": True, "message": "Connected successfully (Mock). Enterprise: Grand Hotel NYC"}

        try:
            url = f"{self._get_base_url()}/api/connector/v1/configuration/get"
            payload = {
                "ClientToken": client_token,
                "AccessToken": access_token,
                "Client": self._get_client_name()
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10.0)

            if res.status_code in [401, 403]:
                return {"success": False, "message": "Invalid Mews credentials. Please check your tokens."}
            elif res.status_code != 200:
                return {"success": False, "message": f"Mews API returned status: {res.status_code}"}

            json_data = res.json()
            if json_data.get("Enterprise"):
                enterprise_name = json_data["Enterprise"]["Name"]
                return {"success": True, "message": f"Connected successfully. Enterprise: {enterprise_name}"}

            return {"success": False, "message": "Invalid response from Mews API."}
        except Exception as e:
            return {"success": False, "message": f"Mews API is currently unavailable: {str(e)}"}

    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        client_token = credentials.get("client_token")
        access_token = credentials.get("access_token")

        if client_token == "mock_client_token" or (client_token and client_token.startswith("mock")):
            return [
                {
                    "external_id": "mews-res-1102",
                    "status": "confirmed",
                    "guest_name": "Jane Smith",
                    "guest_email": "jane.smith@example.com",
                    "guest_phone": "+1-555-0155",
                    "room_number": "202",
                    "room_type": "Deluxe Suite",
                    "check_in_date": datetime.fromisoformat(from_date),
                    "check_out_date": datetime.fromisoformat(to_date),
                    "num_nights": 3,
                    "num_adults": 1,
                    "num_children": 1,
                    "total_amount": 540.0,
                    "currency": "USD",
                    "booking_source": "Expedia",
                    "special_requests": "Gluten free breakfast.",
                    "booked_at": datetime.now()
                }
            ]

        try:
            url = f"{self._get_base_url()}/api/connector/v1/reservations/getAll"
            payload = {
                "ClientToken": client_token,
                "AccessToken": access_token,
                "Client": self._get_client_name(),
                "StartUtc": f"{from_date}T00:00:00Z",
                "EndUtc": f"{to_date}T23:59:59Z",
                "Limitation": {"Count": 100}
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch Mews reservations: {res.reason_phrase}")

            json_data = res.json()
            mews_reservations = json_data.get("Reservations", [])
            mews_customers = json_data.get("Customers", [])
            mews_resources = json_data.get("Resources", [])

            customer_map = {cust["Id"]: cust for cust in mews_customers}
            resource_map = {res["Id"]: res for res in mews_resources}
            unified = []

            for reservation in mews_reservations:
                customer = customer_map.get(reservation.get("CustomerId"), {})
                resource = resource_map.get(reservation.get("AssignedResourceId"), {})

                # Slice UTC string or replace Z
                check_in = datetime.fromisoformat(reservation["StartUtc"].replace("Z", "+00:00"))
                check_out = datetime.fromisoformat(reservation["EndUtc"].replace("Z", "+00:00"))
                num_nights = (check_out - check_in).days or 1

                # Map status: State -> status
                state = reservation.get("State")
                status = "confirmed"
                if state == "Cancelled":
                    status = "cancelled"
                elif state == "Started":
                    status = "checked_in"
                elif state == "Used":
                    status = "checked_out"

                guest_name = f"{customer.get('FirstName', '')} {customer.get('LastName', 'Unknown Guest')}".strip()
                if not guest_name:
                    guest_name = "Unknown Guest"

                total_amount = float(reservation.get("TotalAmount", {}).get("Value", 0.0))

                unified.append({
                    "external_id": str(reservation["Id"]),
                    "status": status,
                    "guest_name": guest_name,
                    "guest_email": customer.get("EmailAddress"),
                    "guest_phone": customer.get("PhoneNumber"),
                    "room_number": resource.get("Name", "Unassigned"),
                    "room_type": resource.get("CategoryName", "Standard"),
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": reservation.get("AdultCount", 1),
                    "num_children": reservation.get("ChildCount", 0),
                    "total_amount": total_amount,
                    "currency": reservation.get("TotalAmount", {}).get("Currency", "USD"),
                    "booking_source": reservation.get("Source", "Mews Engine"),
                    "special_requests": reservation.get("Notes"),
                    "booked_at": datetime.fromisoformat(reservation["CreatedUtc"].replace("Z", "+00:00")) if "CreatedUtc" in reservation else datetime.now()
                })

            return unified
        except Exception as e:
            print(f"Error fetching Mews reservations: {e}")
            raise e

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        client_token = credentials.get("client_token")
        access_token = credentials.get("access_token")

        if client_token == "mock_client_token" or (client_token and client_token.startswith("mock")):
            return [
                {
                    "room_id": "room-202",
                    "date": from_date,
                    "is_available": True,
                    "rate": 180.0
                }
            ]

        try:
            url = f"{self._get_base_url()}/api/connector/v1/resources/getAll"
            payload = {
                "ClientToken": client_token,
                "AccessToken": access_token,
                "Client": self._get_client_name()
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15.0)

            if res.status_code != 200:
                raise Exception(f"Failed to fetch Mews resources: {res.reason_phrase}")

            json_data = res.json()
            mews_resources = json_data.get("Resources", [])
            availability_list = []

            for resource in mews_resources:
                state = resource.get("State")
                availability_list.append({
                    "room_id": str(resource["Id"]),
                    "date": from_date,
                    "is_available": state in ["Active", "Normal"],
                    "rate": 150.0  # Fallback price
                })

            return availability_list
        except Exception as e:
            print(f"Error fetching Mews availability: {e}")
            raise e
