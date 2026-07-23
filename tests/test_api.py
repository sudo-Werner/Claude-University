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


def test_post_events_non_dict_item_returns_400_not_500(client):
    resp = client.post("/api/events", json={"events": ["not-a-dict"]})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_profile_roundtrip(client):
    assert client.get("/api/profile").get_json() == {}
    client.post("/api/profile", json={"analogies": True})
    latest = client.get("/api/profile").get_json()
    assert latest["data"] == {"analogies": True}


def test_stats_streak_from_study_events(client):
    client.post("/api/events", json={"events": [{
        "client_event_id": "st1", "session_id": "s1",
        "event_type": "lesson_view", "occurred_at": "2026-06-21T10:00:00+00:00",
    }]})
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["streakDays"], int)
    assert body["streakCadence"] == "daily"   # default with no profile set


def test_stats_streak_defaults_to_daily_with_no_profile(client):
    resp = client.get("/api/stats")
    assert resp.get_json()["streakCadence"] == "daily"


def test_stats_streak_switches_to_weekly_cadence_from_profile(client):
    client.post("/api/profile", json={"analogies": True, "streakCadence": "weekly"})
    client.post("/api/events", json={"events": [{
        "client_event_id": "st2", "session_id": "s1",
        "event_type": "lesson_view", "occurred_at": "2026-06-21T10:00:00+00:00",
    }]})
    resp = client.get("/api/stats")
    body = resp.get_json()
    assert body["streakCadence"] == "weekly"
    assert isinstance(body["streakDays"], int)


def test_stats_streak_ignores_invalid_cadence_value(client):
    client.post("/api/profile", json={"streakCadence": "monthly"})
    resp = client.get("/api/stats")
    assert resp.get_json()["streakCadence"] == "daily"


def test_stats_streak_tolerates_non_dict_profile_data(client):
    client.post("/api/profile", json=["not", "a", "dict"])
    resp = client.get("/api/stats")  # must not 500
    assert resp.status_code == 200
    assert resp.get_json()["streakCadence"] == "daily"


def test_stats_includes_heatmap_past_and_forecast(client, tmp_path, monkeypatch):
    from backend import courses
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path / "content")
    client.post("/api/events", json={"events": [{
        "client_event_id": "hm1", "session_id": "s1",
        "event_type": "lesson_view", "occurred_at": "2026-07-15T10:00:00+00:00",
    }]})
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["heatmap"]["past"]["2026-07-15"] == 1
    assert body["heatmap"]["forecast"] == {}


def test_activity_returns_resolved_entries(client, tmp_path, monkeypatch):
    import json as _json
    from backend import courses
    root = tmp_path / "content"
    d = root / "c1"
    d.mkdir(parents=True)
    (d / "course.json").write_text(_json.dumps({
        "id": "c1", "title": "Machine Learning",
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "c1-l1", "title": "Intro"}]}],
    }))
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    client.post("/api/events", json={"events": [{
        "client_event_id": "ac1", "session_id": "s1", "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00", "course_id": "c1", "topic_id": "c1-l1",
    }]})
    resp = client.get("/api/activity?limit=10")
    assert resp.status_code == 200
    entries = resp.get_json()["activity"]
    assert entries[0]["courseTitle"] == "Machine Learning"
    assert entries[0]["lessonTitle"] == "Intro"


def test_activity_limit_is_bounded_and_tolerant(client):
    assert client.get("/api/activity?limit=99999").status_code == 200
    assert client.get("/api/activity?limit=banana").status_code == 200


def test_activity_negative_limit_is_clamped(client):
    for i in range(3):
        client.post("/api/events", json={"events": [{
            "client_event_id": f"neg{i}", "session_id": "s1", "event_type": "lesson_view",
            "occurred_at": f"2026-06-21T10:0{i}:00+00:00",
        }]})
    resp = client.get("/api/activity?limit=-1")
    assert resp.status_code == 200
    assert len(resp.get_json()["activity"]) == 1


def test_csp_header_on_index(client):
    csp = client.get("/").headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "script-src 'self';" in csp        # script-src is exactly 'self' — no unsafe-inline
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp


def test_csp_header_on_api(client):
    assert client.get("/api/courses").headers.get("Content-Security-Policy") is not None


def test_style_src_allows_inline_but_script_src_does_not(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    style_dir = [d for d in csp.split(";") if "style-src" in d][0]
    script_dir = [d for d in csp.split(";") if "script-src" in d][0]
    assert "unsafe-inline" in style_dir
    assert "unsafe-inline" not in script_dir


def test_img_src_allows_data_uri_for_inline_svg_icons(client):
    # The .logo::after brand glyph is an inline data: SVG background (styles.css);
    # img-src must allow data: or the logo is CSP-blocked. data: images are
    # script-inert, so this does not weaken script-src (which stays exactly 'self').
    csp = client.get("/").headers["Content-Security-Policy"]
    img_dir = [d for d in csp.split(";") if "img-src" in d][0]
    assert "data:" in img_dir
    script_dir = [d for d in csp.split(";") if "script-src" in d][0]
    assert "data:" not in script_dir  # data: is IMG-only, never scripts
