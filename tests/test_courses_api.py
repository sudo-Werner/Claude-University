import json


def _fixture_course(courses, root):
    """Create a course manifest plus one written lesson file in a temp content dir.

    Writing the lesson file means the lesson GET serves it from disk — it does NOT
    hit the just-in-time generator (which would call real Claude). A lesson id that
    is NOT in the manifest returns 404 from ensure_lesson before any generation.
    """
    manifest = courses.write_course(root, {
        "title": "Test Topic",
        "subtitle": "a test course",
        "brief": "ctx",
        "modules": [{"title": "Module One", "lessons": [{"title": "Lesson One"}]}],
    })
    lesson_id = manifest["modules"][0]["lessons"][0]["id"]
    lesson = {
        "id": lesson_id, "courseId": manifest["id"], "topic": "Topic One",
        "step": 1, "totalSteps": 1, "eyebrow": "EXERCISE",
        "promptHtml": "p", "hintHtml": "h", "solutionAns": "a", "solutionNote": "n",
    }
    (root / manifest["id"] / "lessons" / f"{lesson_id}.json").write_text(json.dumps(lesson))
    return manifest, lesson_id


def test_list_courses_returns_created_course(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)

    listed = client.get("/api/courses").get_json()["courses"]
    found = next(c for c in listed if c["id"] == manifest["id"])
    assert found["title"] == "Test Topic"
    assert found["progress"]["total"] == 1
    assert found["nextLesson"]["id"] == lesson_id


def test_get_course_manifest(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)

    resp = client.get(f"/api/courses/{manifest['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["modules"][0]["title"] == "Module One"


def test_get_lesson_and_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    ok = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert ok.status_code == 200
    assert ok.get_json()["topic"] == "Topic One"
    # unknown lesson id is not in the manifest -> 404 (no generation)
    assert client.get(f"/api/courses/{cid}/lessons/nope").status_code == 404
    # unknown course -> 404
    assert client.get("/api/courses/nope").status_code == 404


def test_post_course_creates_and_lists(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.post("/api/courses", json={
        "title": "Test Course",
        "subtitle": "sub",
        "brief": "ctx",
        "modules": [{"title": "M1", "lessons": [{"title": "L1"}]}],
    })
    assert resp.status_code == 201
    created = resp.get_json()["course"]
    assert created["id"] == "test-course"

    listed = client.get("/api/courses").get_json()["courses"]
    assert any(c["id"] == "test-course" for c in listed)


def test_post_course_rejects_missing_fields(client, tmp_path, monkeypatch):
    from backend import courses
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path / "courses")
    assert client.post("/api/courses", json={"title": "x"}).status_code == 400
    assert client.post("/api/courses", json={"modules": []}).status_code == 400


def test_routes_reject_illegal_ids(client):
    assert client.get("/api/courses/Bad_Id").status_code == 404
    assert client.get("/api/courses/machine-learning/lessons/..%2fsecret").status_code == 404


def test_get_course_includes_mastery(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    resp = client.get(f"/api/courses/{manifest['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "mastery" in body
    assert "masteryCounts" in body
    assert set(body["masteryCounts"].keys()) == {"attempted", "familiar", "proficient", "mastered"}


def test_lesson_route_returns_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, generation
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "Auth Demo", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    # no lesson file on disk -> generation path; force an auth failure
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.get(f"/api/courses/{cid}/lessons/{lid}")
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_reviews_endpoint_lists_due(client, tmp_path, monkeypatch):
    from backend import courses, events, db
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)

    # insert a long-past review into the SAME db the client app uses
    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-1", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2020-01-01T09:00:00+00:00", "course_id": manifest["id"],
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()

    due = client.get(f"/api/courses/{manifest['id']}/reviews").get_json()["due"]
    assert due == [lesson_id]
    listed = client.get("/api/courses").get_json()["courses"]
    found = next(c for c in listed if c["id"] == manifest["id"])
    assert found["reviewsDue"] == 1


def test_grade_endpoint_returns_verdict(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, **kw: {"verdict": "close", "note": "Good start; tighten X."})
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/grade",
                       json={"answer": "my attempt"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["verdict"] == "close"
    assert "tighten" in body["note"].lower()


def test_grade_endpoint_rejects_empty_answer(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/grade", json={"answer": "   "})
    assert resp.status_code == 400


def test_grade_endpoint_missing_lesson_404(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    resp = client.post(f"/api/courses/{cid}/lessons/nope/grade", json={"answer": "x"})
    assert resp.status_code == 404


def test_grade_endpoint_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/grade", json={"answer": "x"})
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_deepen_endpoint_regenerates_lesson(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    deeper = {"id": "x", "courseId": "x", "topic": "t", "step": 9, "totalSteps": 9,
              "eyebrow": "EXERCISE", "promptHtml": "<p>deeper now</p>", "hintHtml": "h",
              "solutionAns": "a", "solutionNote": "n",
              "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}]}
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: deeper)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/deepen")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["promptHtml"] == "<p>deeper now</p>"
    assert body["id"] == lesson_id  # reconciled


def test_deepen_endpoint_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/deepen")
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_deepen_endpoint_404_for_unknown_lesson(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: {})
    resp = client.post(f"/api/courses/{cid}/lessons/nope/deepen")
    assert resp.status_code == 404
