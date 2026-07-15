import json

from backend import app as app_module, claude_client, compiler, courses

OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
COMPILED = {"schemaVersion": 2, "title": "Deep ML", "subtitle": "s", "brief": "b",
    "learnerBrief": {"goal": "g"}, "level": {"code": "master", "label": "Master-equivalent"},
    "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ], "groundingSources": [],
    "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ],
                 "lessons": [{"id": "l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []}]}]}

def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path)
    app = app_module.create_app(db_path=str(tmp_path / "t.db"))
    return app.test_client()

def test_compile_returns_proposed_course_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler, "compile_course", lambda brief, **kw: COMPILED)
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses/compile", json={"learnerBrief": {"goal": "build models"}})
    assert resp.status_code == 200
    assert resp.get_json()["course"]["level"]["code"] == "master"
    assert not (tmp_path / "deep-ml").exists()                     # NOT saved

def test_compile_requires_goal(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/courses/compile", json={"learnerBrief": {}}).status_code == 400

def test_compile_maps_claude_errors(tmp_path, monkeypatch):
    def boom(brief, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(compiler, "compile_course", boom)
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/courses/compile", json={"learnerBrief": {"goal": "g"}})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"

def test_post_courses_writes_compiled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses", json=COMPILED)
    assert resp.status_code == 201
    assert resp.get_json()["course"]["schemaVersion"] == 2
    assert (tmp_path / "deep-ml" / "course.json").exists()


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
    monkeypatch.setattr(claude_client, "run_sourced", boom)
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
              "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}],
              "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                          "answer": 0, "explanation": "Because."}}
    # deepen now generates WITH web search: run_sourced returns (lesson, captured_sources)
    monkeypatch.setattr(claude_client, "run_sourced", lambda prompt, **kw: (deeper, []))
    # ...then a non-web verification pass reconciles it; the reviewer returns it unchanged here.
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: dict(deeper))
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/deepen")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["promptHtml"] == "<p>deeper now</p>"
    assert body["id"] == lesson_id  # reconciled
    assert body["sources"] == []  # no captured sources -> empty list


def test_deepen_endpoint_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_sourced", boom)
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


def _capstone_course(courses, root):
    manifest = courses.write_course(root, {
        "title": "Cap Course", "subtitle": "s", "brief": "b",
        "modules": [{"title": "Mod A", "lessons": [{"title": "L1"}, {"title": "L2"}]}]})
    return manifest, manifest["modules"][0]["id"]


def test_capstone_endpoint_module_scope(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, mid = _capstone_course(courses, root)
    cid = manifest["id"]
    payload = {"intro": "Real world.", "items": [
        {"title": "AlphaFold", "detail": "predicts proteins", "source": "DeepMind"},
        {"title": "GPS", "detail": "uses it", "source": "Wikipedia"}]}
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: payload)
    resp = client.get(f"/api/courses/{cid}/capstone/{mid}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scope"] == mid and body["title"] == "Mod A"
    assert len(body["items"]) == 2


def test_capstone_endpoint_course_scope(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _capstone_course(courses, root)
    cid = manifest["id"]
    payload = {"intro": "i", "items": [
        {"title": "a", "detail": "d", "source": "s"}, {"title": "b", "detail": "d", "source": "s"}]}
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: payload)
    resp = client.get(f"/api/courses/{cid}/capstone/course")
    assert resp.status_code == 200
    assert resp.get_json()["scope"] == "course"


def test_capstone_endpoint_unknown_module_404(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _capstone_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: {})
    resp = client.get(f"/api/courses/{cid}/capstone/m99")
    assert resp.status_code == 404


def test_capstone_endpoint_reauth(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, mid = _capstone_course(courses, root)
    cid = manifest["id"]
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.get(f"/api/courses/{cid}/capstone/{mid}")
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_library_endpoint_returns_filtered_sources(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    captured = [{"title": "arXiv", "url": "https://arxiv.org/abs/1404.7828"}]
    obj = {"sources": [
        {"title": "arXiv", "url": "https://arxiv.org/abs/1404.7828", "note": "survey"},
        {"title": "Fake", "url": "https://nope.example.com/x", "note": "hallucinated"}]}
    monkeypatch.setattr(claude_client, "run_sourced", lambda prompt, **kw: (obj, captured))
    resp = client.get(f"/api/courses/{cid}/library")
    assert resp.status_code == 200
    body = resp.get_json()
    urls = [s["url"] for s in body["sources"]]
    assert "https://arxiv.org/abs/1404.7828" in urls
    assert "https://nope.example.com/x" not in urls
    assert body["sources"][0]["type"] == "peer-reviewed"


def test_library_endpoint_reauth(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_sourced", boom)
    resp = client.get(f"/api/courses/{cid}/library")
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_library_endpoint_404_unknown_course(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.get("/api/courses/no-such-course/library")
    assert resp.status_code == 404


def test_library_endpoint_includes_lesson_source_rollup(client, tmp_path, monkeypatch):
    import json as _json
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    # a generated lesson on disk carries its own cited sources
    lp = root / cid / "lessons" / f"{lesson_id}.json"
    data = _json.loads(lp.read_text())
    data["sources"] = [{"title": "MIT OCW", "url": "https://mit.edu/ocw", "type": "university"}]
    lp.write_text(_json.dumps(data))
    captured = [{"title": "arXiv", "url": "https://arxiv.org/abs/1"}]
    obj = {"sources": [{"title": "arXiv", "url": "https://arxiv.org/abs/1", "note": "n"}]}
    monkeypatch.setattr(claude_client, "run_sourced", lambda prompt, **kw: (obj, captured))
    body = client.get(f"/api/courses/{cid}/library").get_json()
    # subject bibliography (from search) + the live roll-up of lesson sources
    assert any(s["url"] == "https://arxiv.org/abs/1" for s in body["sources"])
    assert any(s["url"] == "https://mit.edu/ocw" for s in body["lessonSources"])


def test_workspace_get_default_and_put_roundtrip(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json() == {
        "notes": "", "chat": [], "updatedAt": None}
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and r.get_json()["updatedAt"]
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["notes"] == "n" and got["chat"][0]["content"] == "hi"


def test_workspace_put_rejects_bad_and_oversize(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                      json={"notes": "n", "chat": [{"role": "x", "content": "y"}]}).status_code == 400
    assert client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                      json={"notes": "z" * 200000, "chat": []}).status_code == 413


def test_workspace_rejects_bad_ids(client):
    assert client.get("/api/courses/Bad_Id/lessons/l1/workspace").status_code == 404


def test_lesson_chat_route_streams(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "stream", lambda prompt, **kw: iter(["Hello ", "world"]))
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "event: delta" in text and "Hello" in text and "event: done" in text


def test_lesson_chat_route_404_unknown_lesson(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/lessons/nope/chat", json={"messages": []}).status_code == 404


# ---------------------------------------------------------------------------
# /revise and /apply-revision
# ---------------------------------------------------------------------------

def test_revise_happy_path(tmp_path, monkeypatch):
    """
    /revise returns proposed course + changeSummary + progressAtRisk (for the dropped completed
    lesson) and does NOT write course.json to disk.
    """
    manifest = courses.write_course(tmp_path, COMPILED)
    cid = manifest["id"]
    # The two lessons in COMPILED get slugged to <cid>-l1 and <cid>-l2 by write_course.
    lesson_ids = [l["id"] for m in manifest["modules"] for l in m["lessons"]]
    assert len(lesson_ids) == 1, f"Expected 1 lesson, got {lesson_ids}"
    kept_id = lesson_ids[0]

    # Write COMPILED with two lessons so we have a "kept" and a "dropped" lesson.
    two_lesson_proposal = {
        **COMPILED,
        "modules": [{
            **COMPILED["modules"][0],
            "lessons": [
                COMPILED["modules"][0]["lessons"][0],
                {"id": "l2", "title": "B", "estMinutes": 60, "objectives": [OBJ], "prereqs": []},
            ],
        }],
    }
    manifest = courses.write_course(tmp_path, two_lesson_proposal)
    cid = manifest["id"]
    lesson_ids = [l["id"] for m in manifest["modules"] for l in m["lessons"]]
    kept_id, dropped_id = lesson_ids[0], lesson_ids[1]
    dropped_title = [l["title"] for m in manifest["modules"] for l in m["lessons"] if l["id"] == dropped_id][0]

    client = _client(tmp_path, monkeypatch)

    # Seed a lesson_completed event for the lesson we'll drop from the revision.
    seed_resp = client.post("/api/events", json={"events": [{
        "client_event_id": "ev-drop-1",
        "session_id": "sess-1",
        "event_type": "lesson_completed",
        "occurred_at": "2026-01-01T10:00:00+00:00",
        "course_id": cid,
        "topic_id": dropped_id,
    }]})
    assert seed_resp.status_code == 200

    # Proposed course keeps only the first lesson (drops the completed second one).
    proposed = {
        **manifest,
        "modules": [{
            **manifest["modules"][0],
            "lessons": [l for l in manifest["modules"][0]["lessons"] if l["id"] == kept_id],
        }],
        "changeSummary": ["Removed lesson B to tighten scope"],
    }

    monkeypatch.setattr(compiler, "revise_course",
                        lambda existing, messages, **kw: proposed)

    on_disk_before = (tmp_path / cid / "course.json").read_text()

    resp = client.post(f"/api/courses/{cid}/revise", json={"messages": [{"role": "user", "content": "remove lesson B"}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["changeSummary"] == ["Removed lesson B to tighten scope"]
    assert len(body["progressAtRisk"]) == 1
    assert body["progressAtRisk"][0]["id"] == dropped_id
    assert body["progressAtRisk"][0]["title"] == dropped_title
    # course.json must be unchanged (non-persisting)
    assert (tmp_path / cid / "course.json").read_text() == on_disk_before


def test_revise_claude_error_handling(tmp_path, monkeypatch):
    """ClaudeAuthError -> 503 reauth, ClaudeError -> 502."""
    manifest = courses.write_course(tmp_path, COMPILED)
    cid = manifest["id"]
    client = _client(tmp_path, monkeypatch)

    def boom_auth(existing, messages, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(compiler, "revise_course", boom_auth)
    r = client.post(f"/api/courses/{cid}/revise", json={"messages": []})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"

    def boom_err(existing, messages, **kw):
        raise claude_client.ClaudeError("fail")
    monkeypatch.setattr(compiler, "revise_course", boom_err)
    r = client.post(f"/api/courses/{cid}/revise", json={"messages": []})
    assert r.status_code == 502


def test_revise_404_for_missing_course(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/courses/no-such-course/revise", json={}).status_code == 404


def test_revise_404_for_illegal_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/courses/Bad_Id!/revise", json={}).status_code == 404


def test_apply_revision_persists_and_rejects_bad(tmp_path, monkeypatch):
    """
    POST /apply-revision with a valid revised course writes course.json;
    a tampered one (wrong id) returns 400.
    """
    manifest = courses.write_course(tmp_path, COMPILED)
    cid = manifest["id"]
    client = _client(tmp_path, monkeypatch)

    # Valid revision — same id, same lesson ids (no new ones), valid schema.
    revised = {**manifest, "title": "Deep ML (Revised)"}
    r = client.post(f"/api/courses/{cid}/apply-revision", json={"course": revised})
    assert r.status_code == 200
    on_disk = json.loads((tmp_path / cid / "course.json").read_text())
    assert on_disk["title"] == "Deep ML (Revised)"

    # Tampered: wrong course id inside the payload -> 400.
    tampered = {**revised, "id": "wrong-id"}
    r = client.post(f"/api/courses/{cid}/apply-revision", json={"course": tampered})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid revision"


def test_apply_revision_404_for_illegal_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/courses/Bad_Id!/apply-revision", json={}).status_code == 404


# ---- #5 explain-it-back grading ----

def test_explain_route_grades_explanation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import json as _json
    d = tmp_path / "c1" / "lessons"
    d.mkdir(parents=True)
    (d / "c1-l1.json").write_text(_json.dumps({
        "id": "c1-l1", "promptHtml": "<p>Body</p>", "solutionAns": "42", "solutionNote": "why",
    }))
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None: {"verdict": "correct", "note": "well put"})
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={"explanation": "because 42"})
    assert resp.status_code == 200
    assert resp.get_json() == {"verdict": "correct", "note": "well put"}


def test_explain_route_requires_explanation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={})
    assert resp.status_code == 400
