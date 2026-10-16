"""
Room import, adapter side: Mews/Cloudbeds fetch_rooms against stored fixtures
shaped like the provider docs (each fixture names its source page). No
network: requests go through httpx.MockTransport.
"""
import json
from pathlib import Path

import httpx

from app.services.adapters import get_adapter
from app.services.adapters.cloudbeds import CloudbedsAdapter
from app.services.adapters.mews import MewsAdapter

FIXTURES = Path(__file__).parent / "fixtures"
MEWS_ROOM_ROUTES = {
    "/api/connector/v1/services/getAll": "services.json",
    "/api/connector/v1/resourceCategories/getAll": "resource_categories_rooms.json",
    "/api/connector/v1/resourceCategoryAssignments/getAll": "resource_category_assignments.json",
    "/api/connector/v1/resources/getAll": "resources.json",
}


def _fixture(provider, name):
    return json.loads((FIXTURES / provider / name).read_text(encoding="utf-8"))


def _mews():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        return httpx.Response(200, json=_fixture("mews", MEWS_ROOM_ROUTES[request.url.path]))

    return MewsAdapter(transport=httpx.MockTransport(handler)), calls


# --- adapters ---------------------------------------------------------------

def test_only_mews_and_cloudbeds_support_room_sync():
    supported = {p for p in ("channex", "mews", "cloudbeds", "siteminder", "little_hotelier")
                 if get_adapter(p).supports_room_sync}
    assert supported == {"mews", "cloudbeds"}


async def test_mews_rooms_follow_bookable_services_and_room_categories():
    adapter, calls = _mews()
    rooms = await adapter.fetch_rooms({"client_token": "real", "access_token": "real"})

    assert rooms == [
        {"external_id": "20e00c32-d561-4008-8609-82d8aa525714", "room_number": "101", "room_type": "Double Room"},
        {"external_id": "1ec29188-01ca-4294-9983-fac59f85a448", "room_number": "102", "room_type": "Double Room"},
    ]
    bodies = dict(calls)
    assert bodies["/api/connector/v1/services/getAll"]["ServiceType"] == "Bookable"
    # inactive service dropped before categories are requested
    assert bodies["/api/connector/v1/resourceCategories/getAll"]["ServiceIds"] == ["bd26d8db-86da-4f96-9efc-e5a4654a4a94"]
    # ParkingSpot category is not asked for
    assert bodies["/api/connector/v1/resourceCategoryAssignments/getAll"]["ResourceCategoryIds"] == [
        "773d5e42-de1e-43a0-9ce6-f940faf2303f"]
    # inactive assignment's resource is not requested
    res_body = bodies["/api/connector/v1/resources/getAll"]
    assert sorted(res_body["ResourceIds"]) == sorted([
        "20e00c32-d561-4008-8609-82d8aa525714", "1ec29188-01ca-4294-9983-fac59f85a448"])
    assert res_body["Extent"] == {"Resources": True, "Inactive": False}
    assert all(b["Limitation"]["Count"] == 1000 for b in bodies.values())


async def test_mews_mock_credentials_import_no_rooms():
    def handler(request):
        raise AssertionError("mock credentials must not hit the network")

    adapter = MewsAdapter(transport=httpx.MockTransport(handler))
    assert await adapter.fetch_rooms({"client_token": "mock_client_token", "access_token": "x"}) == []


async def test_cloudbeds_rooms_parse_nested_rooms_and_skip_virtual():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_fixture("cloudbeds", "get_rooms.json"))

    adapter = CloudbedsAdapter(transport=httpx.MockTransport(handler))
    rooms = await adapter.fetch_rooms({"api_key": "real", "property_id": "173"})

    assert rooms == [
        {"external_id": "r-101", "room_number": "101", "room_type": "Queen Deluxe"},
        {"external_id": "r-102", "room_number": " 102 ", "room_type": "Queen Deluxe"},  # trimmed by the planner
    ]
    assert len(calls) == 1  # 3 rooms < page size: one page
    assert calls[0].url.path.endswith("/getRooms")
    assert calls[0].url.params["propertyIDs"] == "173"


async def test_cloudbeds_rooms_page_until_short_page():
    def room(i):
        return {"roomID": f"r{i}", "roomName": str(i), "roomTypeName": "T", "isVirtual": False}

    pages = {1: [room(i) for i in range(100)], 2: [room(i) for i in range(100, 105)]}
    seen = []

    def handler(request):
        n = int(request.url.params["pageNumber"])
        seen.append(n)
        return httpx.Response(200, json={"success": True, "data": [{"propertyID": "1", "rooms": pages.get(n, [])}],
                                         "count": 1, "total": 105})

    adapter = CloudbedsAdapter(transport=httpx.MockTransport(handler))
    rooms = await adapter.fetch_rooms({"api_key": "real", "property_id": "1"})
    assert len(rooms) == 105
    assert seen == [1, 2]
