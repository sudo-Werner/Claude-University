import json

import pytest

from backend import events


def _ev(cid, **over):
    base = {
        "client_event_id": cid,
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
        "device": "mac",
        "topic_id": "p1t1",
        "payload": {"section": "intro"},
    }
    base.update(over)
    return base


def test_insert_new_events_accepted(conn):
    result = events.insert_events(conn, [_ev("a"), _ev("b")])
    assert result == {"accepted": 2, "duplicates": 0}
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 2


def test_duplicate_client_event_id_ignored(conn):
    events.insert_events(conn, [_ev("a")])
    result = events.insert_events(conn, [_ev("a"), _ev("c")])
    assert result == {"accepted": 1, "duplicates": 1}
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 2


def test_payload_stored_as_json(conn):
    events.insert_events(conn, [_ev("a", payload={"k": 1})])
    row = conn.execute("SELECT payload FROM events WHERE client_event_id='a'").fetchone()
    assert json.loads(row["payload"]) == {"k": 1}


def test_missing_required_field_raises(conn):
    bad = _ev("a")
    del bad["event_type"]
    with pytest.raises(ValueError):
        events.insert_events(conn, [bad])
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 0
