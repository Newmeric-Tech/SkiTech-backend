import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from app.services.adapters.base import BaseAdapter
from app.utils.safe_errors import safe_error_summary

# Mews Connector API references (docs.mews.com/connector-api):
#   reservations  -> operations/reservations#get-all-reservations-ver-2023-06-06
#   resources     -> operations/resources#get-all-resources
#   customers     -> operations/customers#get-all-customers
#   order items   -> operations/orderitems#get-all-order-items
#   categories    -> operations/resourcecategories#get-all-resource-categories
#   age categories-> operations/agecategories#get-all-age-categories
#   paging        -> guidelines/pagination (Limitation.Count max 1000, Cursor)
#   intervals     -> operations/_objects#time-interval (StartUtc inclusive, EndUtc exclusive)

PAGE_SIZE = 1000          # Limitation.Count: "minimum 1, maximum 1000"
MAX_IDS = 1000            # id-list filters are "max 1000 items"
INTERVAL_DAYS = 30        # time filters are "max length 3 months"; stay well inside

# Service order state (reservations doc): Confirmed = before check-in,
# Started = checked in, Processed = checked out, Canceled = canceled.
# Inquired / Optional / Requested fall through to "confirmed" as before.
_STATE_TO_STATUS = {
    "Confirmed": "confirmed",
    "Started": "checked_in",
    "Processed": "checked_out",
    "Canceled": "cancelled",
}

# Resource state (resources doc) values that make a resource unsellable.
_UNAVAILABLE_RESOURCE_STATES = {"OutOfService", "OutOfOrder"}


def _parse_utc(value: str) -> datetime:
    """Mews datetimes are UTC ISO 8601. reservations.check_in/out are
    timestamp WITHOUT time zone, which asyncpg rejects aware datetimes for."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def _localized(text: Optional[Dict[str, str]]) -> Optional[str]:
    """Localized text is a {language code: text} dictionary (_objects doc)."""
    if not text:
        return None
    for lang in ("en-US", "en-GB"):
        if text.get(lang):
            return text[lang]
    return next((v for v in text.values() if v), None)


def _chunks(items: List[str], size: int = MAX_IDS) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


class MewsAdapter(BaseAdapter):

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        # transport is injectable so tests can serve stored fixtures
        self._transport = transport

    def _get_base_url(self) -> str:
        return os.getenv("MEWS_BASE_URL", "https://api.mews-demo.com")

    def _get_client_name(self) -> str:
        return 'TEST Mews Channel Manager Connection'

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=timeout)

    def _auth(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ClientToken": credentials.get("client_token"),
            "AccessToken": credentials.get("access_token"),
            "Client": self._get_client_name(),
        }

    async def _get_all(
        self, client: httpx.AsyncClient, path: str, payload: Dict[str, Any], key: str
    ) -> List[Dict[str, Any]]:
        """Page through a Mews getAll operation. Per the pagination guideline the
        response Cursor is passed back in Limitation until a page comes back
        short or Cursor is null."""
        items: List[Dict[str, Any]] = []
        cursor = None
        while True:
            limitation = {"Count": PAGE_SIZE}
            if cursor:
                limitation["Cursor"] = cursor
            res = await client.post(
                f"{self._get_base_url()}{path}",
                json={**payload, "Limitation": limitation},
                headers={"Content-Type": "application/json"},
            )
            if res.status_code != 200:
                raise Exception(f"Mews {path} failed: {res.status_code} {res.reason_phrase}")
            data = res.json()
            page = data.get(key, [])
            items.extend(page)
            cursor = data.get("Cursor")
            if len(page) < PAGE_SIZE or not cursor:
                return items

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

        auth = self._auth(credentials)
        try:
            async with self._client(timeout=15.0) as client:
                reservations = await self._fetch_colliding_reservations(client, auth, from_date, to_date)
                if not reservations:
                    return []

                # The 2023-06-06 reservation carries only ids; resolve them.
                customer_ids = sorted({r["AccountId"] for r in reservations if r.get("AccountType") == "Customer"})
                resource_ids = sorted({r["AssignedResourceId"] for r in reservations if r.get("AssignedResourceId")})
                category_ids = sorted({r["RequestedResourceCategoryId"] for r in reservations if r.get("RequestedResourceCategoryId")})
                service_ids = sorted({r["ServiceId"] for r in reservations if r.get("ServiceId")})
                reservation_ids = [r["Id"] for r in reservations]

                customers: Dict[str, Dict[str, Any]] = {}
                for ids in _chunks(customer_ids):
                    for c in await self._get_all(client, "/api/connector/v1/customers/getAll",
                                                 {**auth, "CustomerIds": ids, "Extent": {"Customers": True}}, "Customers"):
                        customers[c["Id"]] = c

                resources: Dict[str, Dict[str, Any]] = {}
                for ids in _chunks(resource_ids):
                    for r in await self._get_all(client, "/api/connector/v1/resources/getAll",
                                                 {**auth, "ResourceIds": ids, "Extent": {"Resources": True, "Inactive": True}}, "Resources"):
                        resources[r["Id"]] = r

                categories: Dict[str, Dict[str, Any]] = {}
                for ids in _chunks(category_ids):
                    for c in await self._get_all(client, "/api/connector/v1/resourceCategories/getAll",
                                                 {**auth, "ServiceIds": service_ids, "ResourceCategoryIds": ids}, "ResourceCategories"):
                        categories[c["Id"]] = c

                age_classes: Dict[str, str] = {}
                for a in await self._get_all(client, "/api/connector/v1/ageCategories/getAll",
                                             {**auth, "ServiceIds": service_ids}, "AgeCategories"):
                    age_classes[a["Id"]] = a.get("Classification")

                totals: Dict[str, float] = {}
                currencies: Dict[str, str] = {}
                for ids in _chunks(reservation_ids):
                    for item in await self._get_all(client, "/api/connector/v1/orderItems/getAll",
                                                    {**auth, "ServiceOrderIds": ids}, "OrderItems"):
                        if item.get("CanceledUtc"):
                            continue
                        amount = item.get("Amount") or {}
                        order_id = item["ServiceOrderId"]
                        totals[order_id] = totals.get(order_id, 0.0) + float(amount.get("GrossValue") or 0.0)
                        currencies.setdefault(order_id, amount.get("Currency"))

            unified = []
            for reservation in reservations:
                customer = customers.get(reservation.get("AccountId"), {})
                resource = resources.get(reservation.get("AssignedResourceId"), {})
                category = categories.get(reservation.get("RequestedResourceCategoryId"), {})

                check_in = _parse_utc(reservation["ScheduledStartUtc"])
                check_out = _parse_utc(reservation["ScheduledEndUtc"])
                # Count calendar nights: a 14:00 -> 12:00 stay is short of whole days.
                num_nights = (check_out.date() - check_in.date()).days or 1

                state = reservation.get("State")
                status = _STATE_TO_STATUS.get(state, "confirmed")
                if state == "Canceled" and reservation.get("CancellationReason") == "NoShow":
                    status = "no_show"

                guest_name = f"{customer.get('FirstName') or ''} {customer.get('LastName') or ''}".strip() or "Unknown Guest"

                adults = children = 0
                for pc in reservation.get("PersonCounts") or []:
                    if age_classes.get(pc.get("AgeCategoryId")) == "Child":
                        children += pc.get("Count", 0)
                    else:
                        adults += pc.get("Count", 0)

                unified.append({
                    "external_id": str(reservation["Id"]),
                    "status": status,
                    "guest_name": guest_name,
                    "guest_email": customer.get("Email"),
                    "guest_phone": customer.get("Phone"),
                    "room_number": resource.get("Name", "Unassigned"),
                    "room_type": _localized(category.get("Names")) or "Standard",
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "num_nights": num_nights,
                    "num_adults": adults or 1,
                    "num_children": children,
                    "total_amount": round(totals.get(reservation["Id"], 0.0), 2),
                    "currency": currencies.get(reservation["Id"]) or "USD",
                    "booking_source": reservation.get("Origin") or "Mews",
                    "special_requests": None,
                    "booked_at": datetime.fromisoformat(reservation["CreatedUtc"].replace("Z", "+00:00")) if reservation.get("CreatedUtc") else datetime.now()
                })

            return unified
        except Exception as e:
            print(f"Error fetching Mews reservations: {safe_error_summary(e)}")
            raise e

    async def _fetch_colliding_reservations(
        self, client: httpx.AsyncClient, auth: Dict[str, Any], from_date: str, to_date: str
    ) -> List[Dict[str, Any]]:
        """Reservations whose scheduled stay intersects [from_date, to_date],
        which includes guests already in-house on from_date. CollidingUtc is
        capped at 3 months, so the range is walked in INTERVAL_DAYS windows
        and de-duplicated by Id."""
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)  # EndUtc is exclusive
        seen: Dict[str, Dict[str, Any]] = {}
        while start < end:
            window_end = min(start + timedelta(days=INTERVAL_DAYS), end)
            payload = {
                **auth,
                "CollidingUtc": {
                    "StartUtc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "EndUtc": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
            for r in await self._get_all(client, "/api/connector/v1/reservations/getAll/2023-06-06", payload, "Reservations"):
                seen[r["Id"]] = r
            start = window_end
        return list(seen.values())

    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        client_token = credentials.get("client_token")

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
            async with self._client(timeout=15.0) as client:
                # Extent and Limitation are both required by resources/getAll.
                mews_resources = await self._get_all(
                    client, "/api/connector/v1/resources/getAll",
                    {**self._auth(credentials), "Extent": {"Resources": True, "Inactive": False}},
                    "Resources",
                )

            availability_list = []
            for resource in mews_resources:
                availability_list.append({
                    "room_id": str(resource["Id"]),
                    "date": from_date,
                    "is_available": resource.get("IsActive", True) and resource.get("State") not in _UNAVAILABLE_RESOURCE_STATES,
                    "rate": 150.0  # Fallback price
                })

            return availability_list
        except Exception as e:
            print(f"Error fetching Mews availability: {safe_error_summary(e)}")
            raise e
