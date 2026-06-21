def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_post_and_get_events(client):
    payload = {
        "events": [
            {
                "client_event_id": "a",
                "session_id": "s1",
                "event_type": "lesson_view",
                "occurred_at": "2026-06-21T10:00:00+00:00",
                "payload": {"section": "intro"},
            }
        ]
    }
    post = client.post("/api/events", json=payload)
    assert post.status_code == 200
    assert post.get_json() == {"accepted": 1, "duplicates": 0}

    got = client.get("/api/events")
    assert got.status_code == 200
    events = got.get_json()["events"]
    assert len(events) == 1
    assert events[0]["payload"] == {"section": "intro"}


def test_post_events_idempotent_over_http(client):
    ev = {
        "client_event_id": "dup",
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
    }
    client.post("/api/events", json={"events": [ev]})
    second = client.post("/api/events", json={"events": [ev]})
    assert second.get_json() == {"accepted": 0, "duplicates": 1}


def test_post_events_missing_field_returns_400(client):
    bad = {"events": [{"client_event_id": "x", "session_id": "s1"}]}
    resp = client.post("/api/events", json=bad)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_profile_roundtrip(client):
    assert client.get("/api/profile").get_json() == {}
    client.post("/api/profile", json={"analogies": True})
    latest = client.get("/api/profile").get_json()
    assert latest["data"] == {"analogies": True}
