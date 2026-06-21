from backend import events, queries


def _ev(cid, **over):
    base = {
        "client_event_id": cid,
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
        "payload": {"section": "intro"},
    }
    base.update(over)
    return base


def test_query_all(conn):
    events.insert_events(conn, [_ev("a"), _ev("b")])
    rows = queries.query_events(conn)
    assert len(rows) == 2
    assert rows[0]["payload"] == {"section": "intro"}


def test_query_filters_by_session(conn):
    events.insert_events(conn, [_ev("a", session_id="s1"), _ev("b", session_id="s2")])
    rows = queries.query_events(conn, session_id="s2")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_filters_by_type(conn):
    events.insert_events(
        conn, [_ev("a", event_type="lesson_view"), _ev("b", event_type="quiz_answer")]
    )
    rows = queries.query_events(conn, event_type="quiz_answer")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_filters_since(conn):
    events.insert_events(
        conn,
        [
            _ev("a", occurred_at="2026-06-20T10:00:00+00:00"),
            _ev("b", occurred_at="2026-06-22T10:00:00+00:00"),
        ],
    )
    rows = queries.query_events(conn, since="2026-06-21T00:00:00+00:00")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_ordered_by_occurred_at(conn):
    events.insert_events(
        conn,
        [
            _ev("late", occurred_at="2026-06-22T10:00:00+00:00"),
            _ev("early", occurred_at="2026-06-20T10:00:00+00:00"),
        ],
    )
    rows = queries.query_events(conn)
    assert [r["client_event_id"] for r in rows] == ["early", "late"]
