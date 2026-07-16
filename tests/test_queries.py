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


def _pk_ev(cid, course_id="c1", topic_id="l1", text="I think it's about loops", **over):
    base = {
        "client_event_id": cid,
        "session_id": "s1",
        "event_type": "prior_knowledge",
        "course_id": course_id,
        "topic_id": topic_id,
        "occurred_at": "2026-06-21T10:00:00+00:00",
        "payload": {"text": text},
    }
    base.update(over)
    return base


def test_latest_prior_knowledge_returns_newest_valid_event(conn):
    events.insert_events(conn, [
        _pk_ev("a", text="older guess", occurred_at="2026-06-20T10:00:00+00:00"),
        _pk_ev("b", text="newer guess", occurred_at="2026-06-22T10:00:00+00:00"),
    ])
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == "newer guess"


def test_latest_prior_knowledge_skips_malformed_json(conn):
    conn.execute(
        "INSERT INTO events (client_event_id, session_id, device, topic_id, course_id, "
        "event_type, occurred_at, received_at, payload) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        ("bad-1", "s1", "l1", "c1", "prior_knowledge", "2026-06-21T10:00:00+00:00",
         "2026-06-21T10:00:00+00:00", "{not valid json"),
    )
    conn.commit()
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == ""


def test_latest_prior_knowledge_skips_non_dict_payload(conn):
    events.insert_events(conn, [_pk_ev("a", payload=["not", "a", "dict"])])
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == ""


def test_latest_prior_knowledge_skips_non_str_text(conn):
    events.insert_events(conn, [_pk_ev("a", payload={"text": 123})])
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == ""


def test_latest_prior_knowledge_skips_whitespace_only(conn):
    events.insert_events(conn, [_pk_ev("a", payload={"text": "   "})])
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == ""


def test_latest_prior_knowledge_strips_text(conn):
    events.insert_events(conn, [_pk_ev("a", payload={"text": "  I know some basics  "})])
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == "I know some basics"


def test_latest_prior_knowledge_truncates_to_2000_chars(conn):
    long_text = "x" * 2500
    events.insert_events(conn, [_pk_ev("a", payload={"text": long_text})])
    result = queries.latest_prior_knowledge(conn, "c1", "l1")
    assert len(result) == 2000
    assert result == "x" * 2000


def test_latest_prior_knowledge_returns_empty_string_when_none(conn):
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == ""


def test_latest_prior_knowledge_falls_through_a_bad_row_to_an_older_good_one(conn):
    # newest row is malformed JSON; the helper must not stop there — it falls back
    # to the next-newest valid row rather than returning "".
    events.insert_events(conn, [_pk_ev("a", text="good older", occurred_at="2026-06-20T10:00:00+00:00")])
    conn.execute(
        "INSERT INTO events (client_event_id, session_id, device, topic_id, course_id, "
        "event_type, occurred_at, received_at, payload) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        ("bad-1", "s1", "l1", "c1", "prior_knowledge", "2026-06-22T10:00:00+00:00",
         "2026-06-22T10:00:00+00:00", "{not valid json"),
    )
    conn.commit()
    assert queries.latest_prior_knowledge(conn, "c1", "l1") == "good older"
