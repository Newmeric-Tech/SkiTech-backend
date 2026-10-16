"""
Room import, decision side: sync_service.plan_room_sync, the pure function
that decides insert / adopt / update / conflict per fetched room.
"""
from datetime import datetime

from app.services.sync_service import plan_room_sync

INTEG = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def _row(id, number, integration_id=None, external_id=None, deleted=False, owner_active=False):
    return {"id": id, "room_number": number, "deleted_at": datetime(2026, 1, 1) if deleted else None,
            "integration_id": integration_id, "external_id": external_id, "owner_active": owner_active}


def _f(ext, number, room_type="Double"):
    return {"external_id": ext, "room_number": number, "room_type": room_type}


def _by_action(actions):
    return {a["external_id"]: a for a in actions}


def test_no_match_inserts():
    actions, skip = plan_room_sync([], [_f("e1", "101")], INTEG)
    assert skip is None
    assert actions == [{"action": "insert", "external_id": "e1", "room_number": "101", "room_type": "Double"}]


def test_single_trimmed_case_insensitive_match_is_adopted_keeping_local_number():
    actions, _ = plan_room_sync([_row("a", "A-101")], [_f("e1", "  a-101 ")], INTEG)
    assert actions == [{"action": "adopt", "id": "a", "external_id": "e1", "room_number": "A-101", "room_type": "Double"}]


def test_two_candidates_is_a_conflict():
    actions, _ = plan_room_sync([_row("a", "101"), _row("b", "101 ")], [_f("e1", "101")], INTEG)
    assert actions[0]["action"] == "conflict"
    assert "2 existing rooms" in actions[0]["reason"]


def test_soft_deleted_match_is_a_conflict_not_restored():
    actions, _ = plan_room_sync([_row("a", "101", deleted=True)], [_f("e1", "101")], INTEG)
    assert actions[0]["action"] == "conflict"
    assert actions[0]["reason"] == "matches a deleted room"


def test_other_active_integration_owning_rooms_skips_everything():
    existing = [_row("a", "101", integration_id=OTHER, external_id="x", owner_active=True)]
    actions, skip = plan_room_sync(existing, [_f("e1", "201")], INTEG)
    assert actions == [] and skip


def test_room_of_disconnected_integration_can_be_adopted():
    existing = [_row("a", "101", integration_id=OTHER, external_id="x", owner_active=False)]
    actions, skip = plan_room_sync(existing, [_f("e1", "101")], INTEG)
    assert skip is None
    assert actions[0]["action"] == "adopt"


def test_known_room_is_updated_and_renamed():
    existing = [_row("a", "101", integration_id=INTEG, external_id="e1", owner_active=True)]
    actions, _ = plan_room_sync(existing, [_f("e1", "101A", "Suite")], INTEG)
    assert actions == [{"action": "update", "id": "a", "external_id": "e1", "room_number": "101A", "room_type": "Suite"}]


def test_soft_deleted_synced_room_is_a_conflict_not_updated():
    existing = [_row("a", "101", integration_id=INTEG, external_id="e1", deleted=True, owner_active=True)]
    for fetched_number in ("101", "101A"):  # same number, and a rename
        actions, skip = plan_room_sync(existing, [_f("e1", fetched_number)], INTEG)
        assert skip is None
        assert actions == [{"action": "conflict", "external_id": "e1", "room_number": fetched_number,
                            "reason": "matches a deleted room"}]


def test_rename_onto_existing_number_is_a_conflict():
    existing = [_row("a", "101", integration_id=INTEG, external_id="e1", owner_active=True), _row("b", "102")]
    actions, _ = plan_room_sync(existing, [_f("e1", "102")], INTEG)
    assert actions[0]["action"] == "conflict"


def test_duplicate_names_in_one_fetch_insert_once():
    actions, _ = plan_room_sync([], [_f("e1", "101"), _f("e2", "101")], INTEG)
    assert [a["action"] for a in actions] == ["insert", "conflict"]


def test_blank_or_too_long_names_are_conflicts():
    actions, _ = plan_room_sync([], [_f("e1", "   "), _f("e2", "x" * 51)], INTEG)
    assert [a["action"] for a in actions] == ["conflict", "conflict"]


def test_room_type_is_trimmed_and_capped():
    actions, _ = plan_room_sync([], [_f("e1", "101", " " + "t" * 150), _f("e2", "102", "")], INTEG)
    by = _by_action(actions)
    assert by["e1"]["room_type"] == "t" * 100
    assert by["e2"]["room_type"] is None
