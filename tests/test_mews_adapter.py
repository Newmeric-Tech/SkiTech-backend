"""
MewsAdapter against stored fixtures shaped like the Mews Connector API docs
(tests/fixtures/mews, each file names its source page). No network: requests
go through httpx.MockTransport, which also records them for assertions.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx

import app.services.adapters.mews as mews_module
from app.services.adapters.mews import MewsAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "mews"
CREDS = {"client_token": "real-client", "access_token": "real-access"}

ROUTES = {
    "/api/connector/v1/reservations/getAll/2023-06-06": "reservations_2023_06_06.json",
    "/api/connector/v1/customers/getAll": "customers.json",
    "/api/connector/v1/resources/getAll": "resources.json",
    "/api/connector/v1/resourceCategories/getAll": "resource_categories.json",
    "/api/connector/v1/ageCategories/getAll": "age_categories.json",
    "/api/connector/v1/orderItems/getAll": "order_items.json",
}


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_adapter(routes=ROUTES):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        return httpx.Response(200, json=_fixture(routes[request.url.path]))

    return MewsAdapter(transport=httpx.MockTransport(handler)), calls


async def test_reservations_parse_documented_fields():
    adapter, _ = make_adapter()
    out = await adapter.fetch_reservations(CREDS, "prop", "2023-04-23", "2023-04-24")
    by_id = {r["external_id"]: r for r in out}

    started = by_id["0f515589-99b4-423d-b83a-b237009f0509"]
    assert started["status"] == "checked_in"                 # State Started = checked in
    assert started["room_number"] == "101"                   # AssignedResourceId -> Resource.Name
    assert started["room_type"] == "Double Room"             # RequestedResourceCategoryId -> Names
    assert started["guest_name"] == "Fixture Guest"          # AccountId -> Customer
    assert started["guest_email"] == "fixture.guest@example.invalid"
    assert started["check_in_date"] == datetime(2023, 4, 23, 14, 0)   # ScheduledStartUtc
    assert started["check_out_date"] == datetime(2023, 4, 25, 12, 0)  # ScheduledEndUtc
    assert started["check_in_date"].tzinfo is None           # column is timestamp without tz
    assert started["num_nights"] == 2                        # calendar nights, not 46h // 24
    assert (started["num_adults"], started["num_children"]) == (2, 1)  # age category Classification
    assert started["total_amount"] == 300.5                  # GrossValue sum, canceled item excluded
    assert started["currency"] == "EUR"
    assert started["booking_source"] == "ChannelManager"

    no_show = by_id["6c1f2a8e-0000-4d1e-9a51-b237009f0aaa"]
    assert no_show["status"] == "no_show"                    # Canceled + CancellationReason NoShow
    assert no_show["room_number"] == "Unassigned"            # AssignedResourceId is optional
    assert no_show["guest_name"] == "Unknown Guest"          # Company account: no customer lookup


async def test_state_mapping_uses_documented_enum():
    assert mews_module._STATE_TO_STATUS == {
        "Confirmed": "confirmed",
        "Started": "checked_in",
        "Processed": "checked_out",
        "Canceled": "cancelled",
    }


async def test_requests_carry_required_fields_and_ids():
    adapter, calls = make_adapter()
    await adapter.fetch_reservations(CREDS, "prop", "2023-04-23", "2023-04-24")
    paths = [p for p, _ in calls]

    assert "/api/connector/v1/reservations/getAll" not in paths   # deprecated 2017-04-12 version
    for path, body in calls:
        assert body["Limitation"]["Count"] == 1000, path          # Limitation is required everywhere
        assert body["ClientToken"] == "real-client"

    customers_body = next(b for p, b in calls if p.endswith("customers/getAll"))
    assert customers_body["CustomerIds"] == ["fadd5bb6-b428-45d5-94f8-fd0d89fece6d"]  # Company account skipped
    assert customers_body["Extent"] == {"Customers": True}

    resources_body = next(b for p, b in calls if p.endswith("resources/getAll"))
    assert resources_body["Extent"]["Resources"] is True                  # Extent is required
    assert resources_body["ResourceIds"] == ["20e00c32-d561-4008-8609-82d8aa525714"]

    cat_body = next(b for p, b in calls if p.endswith("resourceCategories/getAll"))
    assert cat_body["ServiceIds"] == ["bd26d8db-86da-4f96-9efc-e5a4654a4a94"]  # ServiceIds is required


async def test_colliding_window_is_split_and_end_exclusive():
    adapter, calls = make_adapter()
    await adapter.fetch_reservations(CREDS, "prop", "2026-10-14", "2027-01-12")  # sync's 90-day range
    windows = [b["CollidingUtc"] for p, b in calls if p.endswith("2023-06-06")]

    assert windows[0]["StartUtc"] == "2026-10-14T00:00:00Z"
    assert windows[-1]["EndUtc"] == "2027-01-13T00:00:00Z"    # EndUtc exclusive -> day after to_date
    for prev, nxt in zip(windows, windows[1:]):
        assert prev["EndUtc"] == nxt["StartUtc"]              # contiguous, no gaps
    for w in windows:
        span = datetime.fromisoformat(w["EndUtc"][:-1]) - datetime.fromisoformat(w["StartUtc"][:-1])
        assert span <= timedelta(days=30)                      # well inside the 3-month cap


async def test_paging_follows_cursor(monkeypatch):
    monkeypatch.setattr(mews_module, "PAGE_SIZE", 1)
    pages = [
        {"Reservations": [{"Id": "r2"}], "Cursor": "r2"},
        {"Reservations": [{"Id": "r1"}], "Cursor": "r1"},
        {"Reservations": [], "Cursor": None},
    ]
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body["Limitation"])
        return httpx.Response(200, json=pages[len(sent) - 1])

    adapter = MewsAdapter(transport=httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=adapter._transport) as client:
        items = await adapter._get_all(client, "/x", {}, "Reservations")

    assert [i["Id"] for i in items] == ["r2", "r1"]
    assert sent == [{"Count": 1}, {"Count": 1, "Cursor": "r2"}, {"Count": 1, "Cursor": "r1"}]


async def test_availability_sends_extent_and_maps_resource_state():
    adapter, calls = make_adapter()
    out = await adapter.fetch_availability(CREDS, "prop", "2023-04-23", "2023-04-24")

    path, body = calls[0]
    assert path == "/api/connector/v1/resources/getAll"
    assert body["Extent"] == {"Resources": True, "Inactive": False}
    assert {r["room_id"]: r["is_available"] for r in out} == {
        "20e00c32-d561-4008-8609-82d8aa525714": True,    # Inspected
        "1ec29188-01ca-4294-9983-fac59f85a448": False,   # OutOfOrder
    }


async def test_mock_token_still_bypasses_network():
    def handler(request):
        raise AssertionError("mock credentials must not hit the network")

    adapter = MewsAdapter(transport=httpx.MockTransport(handler))
    out = await adapter.fetch_reservations({"client_token": "mock_client_token"}, "p", "2026-10-14", "2026-10-20")
    assert out[0]["external_id"] == "mews-res-1102"
