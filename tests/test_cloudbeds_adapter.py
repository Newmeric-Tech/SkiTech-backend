"""
CloudbedsAdapter.fetch_reservations against stored fixtures shaped like the
Cloudbeds OpenAPI reference (tests/fixtures/cloudbeds, each file names its
source page). No network: requests go through httpx.MockTransport.
"""
import json
from datetime import datetime
from pathlib import Path

import httpx

import app.services.adapters.cloudbeds as cloudbeds_module
from app.services.adapters.cloudbeds import CloudbedsAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "cloudbeds"
CREDS = {"api_key": "real-key", "property_id": "173"}

ROUTES = {
    "getReservations": "get_reservations.json",
    "getReservationsWithRateDetails": "get_reservations_with_rate_details.json",
}


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_adapter():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        calls.append((endpoint, dict(request.url.params)))
        return httpx.Response(200, json=_fixture(ROUTES[endpoint]))

    return CloudbedsAdapter(transport=httpx.MockTransport(handler)), calls


async def test_reservations_parse_documented_fields():
    adapter, _ = make_adapter()
    out = await adapter.fetch_reservations(CREDS, "ignored", "2023-04-23", "2023-04-24")
    by_id = {r["external_id"]: r for r in out}

    first = by_id["9000001"]
    assert first["status"] == "checked_in"
    assert first["room_number"] == "303"                  # rooms[].roomName, not roomID
    assert first["room_type"] == "Queen Deluxe"           # rooms[].roomTypeName
    assert first["guest_name"] == "Fixture Guest"
    assert first["guest_email"] == "fixture.guest@example.invalid"   # guestList main guest
    assert first["guest_phone"] == "+00 000 000"
    assert (first["num_adults"], first["num_children"]) == (2, 1)    # documented as strings
    assert first["check_in_date"] == datetime(2023, 4, 23)
    assert first["num_nights"] == 2
    assert first["total_amount"] == 412.75                # rate details `total`
    assert first["currency"] == "EUR"                     # rate details `propertyCurrency`
    assert first["booking_source"] == "Booking.com"       # sourceName
    assert first["booked_at"] == datetime(2023, 3, 20, 10, 15)

    second = by_id["9000002"]
    assert second["status"] == "cancelled"                # enum value is "canceled"
    assert second["room_number"] == "N/A"                 # roomID null = not assigned yet
    assert second["guest_email"] is None


async def test_status_map_covers_documented_enum():
    documented = {"not_confirmed", "confirmed", "canceled", "checked_in", "checked_out", "no_show"}
    assert set(cloudbeds_module._STATUS_MAP) == documented


async def test_requests_use_documented_parameters():
    adapter, calls = make_adapter()
    await adapter.fetch_reservations(CREDS, "ignored", "2023-04-23", "2023-04-24")

    endpoint, params = calls[0]
    assert endpoint == "getReservations"
    assert params["checkInFrom"] == "2023-04-23" and params["checkInTo"] == "2023-04-24"
    assert "startDate" not in params and "endDate" not in params   # not getReservations params
    assert params["includeAllRooms"] == "true"
    assert params["includeGuestsDetails"] == "true"
    assert params["propertyID"] == "173"
    assert params["pageSize"] == "100"                              # documented max

    endpoint, params = calls[1]
    assert endpoint == "getReservationsWithRateDetails"
    assert params["reservationID"] == "9000001,9000002"


async def test_paging_runs_past_five_pages(monkeypatch):
    """The old loop stopped at page 5; paging must continue until done."""
    monkeypatch.setattr(cloudbeds_module, "PAGE_SIZE", 1)
    total = 7
    seen_pages = []

    def handler(request):
        endpoint = request.url.path.rsplit("/", 1)[-1]
        page = int(request.url.params["pageNumber"])
        if endpoint == "getReservations":
            seen_pages.append(page)
            data = [{
                "reservationID": str(page), "status": "confirmed", "guestName": "g",
                "startDate": "2023-04-23", "endDate": "2023-04-24", "adults": "1", "children": "0",
            }] if page <= total else []
        else:
            data = []
        return httpx.Response(200, json={"success": True, "data": data, "count": len(data), "total": total})

    adapter = CloudbedsAdapter(transport=httpx.MockTransport(handler))
    out = await adapter.fetch_reservations(CREDS, "ignored", "2023-04-23", "2023-04-24")

    assert len(out) == 7
    assert seen_pages == [1, 2, 3, 4, 5, 6, 7]       # stops at `total`, no extra request


async def test_unsuccessful_body_raises():
    def handler(request):
        return httpx.Response(200, json={"success": False, "message": "Access denied"})

    adapter = CloudbedsAdapter(transport=httpx.MockTransport(handler))
    try:
        await adapter.fetch_reservations(CREDS, "ignored", "2023-04-23", "2023-04-24")
    except Exception as e:
        assert "Access denied" in str(e)
    else:
        raise AssertionError("expected an exception")


async def test_mock_key_still_bypasses_network():
    def handler(request):
        raise AssertionError("mock credentials must not hit the network")

    adapter = CloudbedsAdapter(transport=httpx.MockTransport(handler))
    out = await adapter.fetch_reservations({"api_key": "mock_cloudbeds_key"}, "p", "2026-10-14", "2026-10-20")
    assert out[0]["external_id"] == "cb-res-4402"
