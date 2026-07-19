import json

from backend import app as app_module, claude_client, compiler, courses, exams

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


def test_misconceptions_route_empty_when_none_recorded(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    resp = client.get(f"/api/courses/{manifest['id']}/misconceptions")
    assert resp.status_code == 200
    assert resp.get_json()["entries"] == []


def test_misconceptions_route_404s_unknown_course(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    assert client.get("/api/courses/nope/misconceptions").status_code == 404
    assert client.get("/api/courses/Bad_Id/misconceptions").status_code == 404


def test_explain_route_persists_misconception_and_hides_rubric_from_response(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "verdict": "close", "note": "n", "followUp": "f",
        "accuracy": 80, "clarity": 70, "completeness": 60, "understanding": 75,
        "misconceptions": ["you think gradient descent always finds the global minimum"],
        "strengths": [],
    })
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/explain",
                       json={"explanation": "my explanation of the idea"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {"verdict", "note", "followUp"}  # rubric never reaches the client
    profile = client.get(f"/api/courses/{cid}/misconceptions").get_json()["entries"]
    assert len(profile) == 1
    assert profile[0]["text"] == "you think gradient descent always finds the global minimum"
    assert profile[0]["excerpt"] == "my explanation of the idea"
    assert profile[0]["source"] == "explain"
    assert profile[0]["lessonId"] == lesson_id


def test_explain_route_persistence_failure_does_not_break_the_grade(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, misconceptions as mc
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "verdict": "correct", "note": "n", "followUp": "f",
        "accuracy": 1, "clarity": 1, "completeness": 1, "understanding": 1,
        "misconceptions": ["something"], "strengths": [],
    })
    def boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(mc, "add_entries", boom)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/explain",
                       json={"explanation": "my explanation"})
    assert resp.status_code == 200  # grade succeeds even though persistence blew up
    assert resp.get_json()["verdict"] == "correct"


def test_teach_route_persists_misconception(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "verdict": "close", "note": "n",
        "accuracy": 80, "clarity": 70, "completeness": 60, "understanding": 75,
        "misconceptions": ["you think X"], "strengths": [],
    })
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach",
                       json={"messages": [{"role": "user", "content": "X is always true"}]})
    assert resp.status_code == 200
    assert set(resp.get_json().keys()) == {"verdict", "note"}  # rubric never reaches the client
    profile = client.get(f"/api/courses/{cid}/misconceptions").get_json()["entries"]
    assert len(profile) == 1
    assert profile[0]["source"] == "teach"
    assert profile[0]["excerpt"] == "X is always true"


def test_delete_misconception_route(client, tmp_path, monkeypatch):
    from backend import courses, misconceptions as mc
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    mc.add_entries(root, cid, lesson_id, "Lesson One", "explain", [("text", "excerpt")])
    entry_id = mc.load_profile(root, cid)[0]["id"]
    resp = client.delete(f"/api/courses/{cid}/misconceptions/{entry_id}")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert mc.load_profile(root, cid) == []


def test_delete_misconception_route_404s_unknown_entry(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    manifest, _ = _fixture_course(courses, root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.delete(f"/api/courses/{manifest['id']}/misconceptions/mc-doesnotexist")
    assert resp.status_code == 404


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


def test_get_lesson_attaches_concepts_from_spine(client, tmp_path, monkeypatch):
    from backend import courses, spine
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    spine.save_spine(root, cid, {"lessons": {lesson_id: {
        "summary": "s", "concepts": [{"term": "Gradient", "definition": "d"}]}}})

    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert resp.status_code == 200
    assert resp.get_json()["concepts"] == ["Gradient"]
    # never written into the cached lesson file
    raw = json.loads((root / cid / "lessons" / f"{lesson_id}.json").read_text())
    assert "concepts" not in raw


def test_get_lesson_omits_concepts_without_spine_entry(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert resp.status_code == 200
    assert "concepts" not in resp.get_json()


def test_get_lesson_omits_concepts_when_spine_corrupt(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    (root / cid / "spine.json").write_text("{not json")

    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert resp.status_code == 200
    assert "concepts" not in resp.get_json()


def test_get_lesson_skips_malformed_concept_items(client, tmp_path, monkeypatch):
    from backend import courses, spine
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    spine.save_spine(root, cid, {"lessons": {lesson_id: {
        "summary": "s",
        "concepts": [{"term": "Good", "definition": "d"}, {"term": ""},
                     "not-a-dict", {"definition": "no term"}]}}})

    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert resp.status_code == 200
    assert resp.get_json()["concepts"] == ["Good"]


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
                          "answer": 0, "explanation": "Because."},
              "spine": {"summary": "Teaches what recursion is.",
                        "concepts": [{"term": "recursion",
                                      "definition": "A function calling itself on a smaller input."}]}}
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


def test_deepen_endpoint_attaches_concepts_from_fresh_spine(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    deeper = {"id": lesson_id, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
              "eyebrow": "EXERCISE", "promptHtml": "<p>deeper</p>", "hintHtml": "h",
              "solutionAns": "a", "solutionNote": "n",
              "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}],
              "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                          "answer": 0, "explanation": "Because."},
              "spine": {"summary": "Teaches recursion.",
                        "concepts": [{"term": "recursion",
                                      "definition": "A function calling itself."}]}}
    monkeypatch.setattr(claude_client, "run_sourced", lambda prompt, **kw: (deeper, []))
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: dict(deeper))
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/deepen")
    assert resp.status_code == 200
    assert resp.get_json()["concepts"] == ["recursion"]


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
    assert body["sources"][0]["type"] == "preprint"


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
        "notes": "", "chat": [], "highlights": [], "updatedAt": None}
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


def test_workspace_put_roundtrips_highlights(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    hl = [{"id": "h1", "text": "a phrase", "occurrence": 0}]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [], "highlights": hl})
    assert r.status_code == 200 and r.get_json()["updatedAt"]
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["highlights"] == hl


def test_workspace_put_rejects_bad_highlights(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [], "highlights": [{"id": "h1", "text": "x", "occurrence": -1}]})
    assert r.status_code == 400


def test_workspace_put_without_highlights_key_still_works(client, tmp_path, monkeypatch):
    # Regression: an OLD client that never sends "highlights" at all must behave
    # exactly as before -- notes/chat unaffected, highlights silently defaults to [].
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["notes"] == "n" and got["chat"][0]["content"] == "hi" and got["highlights"] == []


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


def test_lesson_chat_route_passes_solution_revealed(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "stream", lambda prompt, **kw: iter(["ok"]))
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "help"}], "solutionRevealed": True})
    assert resp.status_code == 200


def test_lesson_chat_socratic_mode_swaps_prompt_and_drops_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "step 1?"}],
                             "mode": "socratic"})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)  # drain the lazy SSE generator
    assert "event: done" in text
    prompt, kw = calls[0]
    assert "NEVER state it" in prompt          # socratic system prompt selected
    assert not kw.get("tools")                 # WebSearch/WebFetch dropped


def test_lesson_chat_normal_mode_keeps_web_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    resp.get_data(as_text=True)
    assert calls[0][1].get("tools") == ["WebSearch", "WebFetch"]


def test_lesson_chat_mode_falls_back_to_normal_unless_socratic(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    prompts = []

    def fake_stream(prompt, **kw):
        prompts.append(prompt)
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    for mode in (None, "chat", 5, True):
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        if mode is not None:
            payload["mode"] = mode
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat", json=payload)
        assert resp.status_code == 200
        resp.get_data(as_text=True)
    assert len(prompts) == 4
    for p in prompts:
        assert "never state the answer" in p.lower()          # default system prompt
        assert "NEVER state it" not in p


def test_lesson_chat_forged_bodies_stream_without_500(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "stream", lambda prompt, **kw: iter(["ok"]))
    for payload in ([1, 2], "str", 5, {"messages": "x"}, {"messages": [1, {}]}):
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat", json=payload)
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert "event: done" in text


def test_lesson_chat_analogy_mode_builds_personalized_prompt_without_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, spine, profile as profile_mod, db
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "Analogy Course", "subtitle": "s", "brief": "ctx",
        "learnerBrief": {"goal": "become a chef", "background": "line cook"},
        "modules": [{"title": "Module One", "lessons": [{"title": "Lesson One"}]}]})
    lesson_id = manifest["modules"][0]["lessons"][0]["id"]
    cid = manifest["id"]
    lesson = {
        "id": lesson_id, "courseId": cid, "topic": "Topic One",
        "step": 1, "totalSteps": 1, "eyebrow": "EXERCISE",
        "promptHtml": "p", "hintHtml": "h", "solutionAns": "a", "solutionNote": "n",
    }
    (root / cid / "lessons" / f"{lesson_id}.json").write_text(json.dumps(lesson))
    spine.save_spine(root, cid, {"lessons": {lesson_id: {
        "summary": "Teaches recursion basics.",
        "concepts": [{"term": "Recursion", "definition": "A function calling itself."}]}}})

    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        profile_mod.save_profile(conn, {"analogies": True, "level": "beginner"})
    finally:
        conn.close()

    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(
        f"/api/courses/{cid}/lessons/{lesson_id}/chat",
        json={"messages": [{"role": "user", "content": 'Give me a different way to think about "Recursion".'}],
              "mode": "analogy", "concept": "Recursion"})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "event: delta" in text and "event: done" in text
    prompt, kw = calls[0]
    assert "Recursion" in prompt
    assert "A function calling itself." in prompt
    assert "Teaches recursion basics." in prompt
    assert '"goal": "become a chef"' in prompt
    assert '"analogies": true' in prompt
    assert "not instructions" in prompt
    assert not kw.get("tools")


def test_lesson_chat_analogy_mode_falls_back_when_concept_unresolved(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, spine
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    spine.save_spine(root, cid, {"lessons": {lesson_id: {
        "summary": "s", "concepts": [{"term": "Recursion", "definition": "d"}]}}})
    prompts = []
    calls = []

    def fake_stream(prompt, **kw):
        prompts.append(prompt)
        calls.append(kw)
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    bad_payloads = [
        {"messages": [{"role": "user", "content": "hi"}], "mode": "analogy", "concept": "Not A Real Term"},
        {"messages": [{"role": "user", "content": "hi"}], "mode": "analogy", "concept": 5},
        {"messages": [{"role": "user", "content": "hi"}], "mode": "analogy"},
    ]
    for payload in bad_payloads:
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat", json=payload)
        assert resp.status_code == 200
        resp.get_data(as_text=True)
    assert len(prompts) == 3
    for p in prompts:
        assert "never state the answer" in p.lower()            # default LESSON_CHAT_SYSTEM marker present
        assert "NEVER state it" not in p
        assert "already said" not in p.lower()   # ANALOGY_SYSTEM marker absent
    for kw in calls:
        assert kw.get("tools") == ["WebSearch", "WebFetch"]   # normal-chat tools restored


def test_lesson_chat_analogy_mode_falls_back_when_concepts_null(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, spine
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    spine.save_spine(root, cid, {"lessons": {lesson_id: {
        "summary": "s", "concepts": None}}})
    prompts = []
    calls = []

    def fake_stream(prompt, **kw):
        prompts.append(prompt)
        calls.append(kw)
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "hi"}],
                             "mode": "analogy", "concept": "SomeConceptTerm"})
    assert resp.status_code == 200
    resp.get_data(as_text=True)
    assert len(prompts) == 1
    p = prompts[0]
    assert "never state the answer" in p.lower()            # default LESSON_CHAT_SYSTEM marker present
    assert "NEVER state it" not in p
    assert "already said" not in p.lower()   # ANALOGY_SYSTEM marker absent
    assert calls[0].get("tools") == ["WebSearch", "WebFetch"]   # normal-chat tools restored


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


def test_apply_revision_prunes_review_items(tmp_path, monkeypatch):
    from backend import review_items
    manifest = courses.write_course(tmp_path, COMPILED)
    cid = manifest["id"]
    kept_id = manifest["modules"][0]["lessons"][0]["id"]
    review_items.save_items(tmp_path, cid, {"lessonId": kept_id, "reviewCount": 0, "items": []})
    review_items.save_items(tmp_path, cid, {"lessonId": "ghost-lesson", "reviewCount": 0, "items": []})
    client = _client(tmp_path, monkeypatch)
    revised = {**manifest, "title": "Deep ML (Revised)"}
    r = client.post(f"/api/courses/{cid}/apply-revision", json={"course": revised})
    assert r.status_code == 200
    assert review_items.load_items(tmp_path, cid, kept_id) is not None
    assert review_items.load_items(tmp_path, cid, "ghost-lesson") is None


def test_apply_revision_keeps_misconceptions_for_a_dropped_lesson(tmp_path):
    # Uses the COMPILED fixture (like the sibling apply_revision tests above), not
    # _fixture_course — apply_revision's own valid_compiled_course gate requires
    # schemaVersion 2 + level/targetHours/skills/outcomes, which _fixture_course's
    # bare manifest doesn't carry, so a revision built from it is always rejected
    # regardless of the misconceptions behavior under test here.
    from backend import courses, misconceptions as mc
    root = tmp_path / "courses"; root.mkdir()
    manifest = courses.write_course(root, COMPILED)
    cid = manifest["id"]
    lesson_id = manifest["modules"][0]["lessons"][0]["id"]
    mc.add_entries(root, cid, lesson_id, "Lesson One", "explain", [("kept forever", "ex")])
    revised = {**manifest, "modules": [{"id": "m-new", "title": "New Module", "outcomes": [OBJ],
        "lessons": [{"id": f"{cid}-l99", "title": "New Lesson", "estMinutes": 30, "objectives": [OBJ]}]}]}
    result = courses.apply_revision(root, cid, revised)
    assert result is not None
    profile = mc.load_profile(root, cid)
    assert len(profile) == 1
    assert profile[0]["text"] == "kept forever"  # survives even though its lesson was dropped


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
                        lambda prompt, validate=None: {"verdict": "correct", "note": "well put",
                                                        "followUp": "Why?"})
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={"explanation": "because 42"})
    assert resp.status_code == 200
    assert resp.get_json() == {"verdict": "correct", "note": "well put", "followUp": "Why?"}


def test_explain_route_requires_explanation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={})
    assert resp.status_code == 400


# ---- summative assessment: exam routes ----

def _exam_generate_ok(slots):
    def fake(prompt, *, validate=None, **kw):
        qs = []
        for s in slots:
            q = {"type": s["type"], "lessonId": s["lessonId"], "prompt": "<p>Q?</p>"}
            if s["type"] == "mcq":
                q.update(choices=["a", "b", "c", "d"], answerIndex=0)
            else:
                q.update(modelAnswer="ref", graderNotes="notes")
            qs.append(q)
        obj = {"questions": qs}
        assert validate is None or validate(obj)
        return obj
    return fake


def test_start_exam_returns_stripped_questions(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    resp = client.post(f"/api/courses/{cid}/exams/m1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["examKey"] == "m1" and len(body["questions"]) == 10
    blob = resp.get_data(as_text=True)
    assert "answerIndex" not in blob and "modelAnswer" not in blob and "graderNotes" not in blob
    assert (root / cid / "exams" / "m1.json").exists()


def test_start_exam_unknown_key_404(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    assert client.post(f"/api/courses/{cid}/exams/m99").status_code == 404
    assert client.post("/api/courses/nope/exams/m1").status_code == 404


def test_start_exam_maps_claude_errors(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502


def test_submit_exam_roundtrip(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 200

    def fake_grade(prompt, *, validate=None, **kw):
        import re
        idxs = [int(m) for m in re.findall(r'"index": (\d+)', prompt)]
        return {"grades": [{"index": i, "verdict": "correct", "note": "Good.", "evidence": "ans"}
                           for i in idxs]}

    monkeypatch.setattr(claude_client, "run_structured", fake_grade)
    exam = exams.load_pending(root, cid, "m1")
    answers = [0 if q["type"] == "mcq" else "ans" for q in exam["questions"]]
    resp = client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": answers})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True and body["attempt"] == 1
    # consumed: a second submit finds nothing pending
    assert client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": answers}).status_code == 404


def test_submit_exam_bad_answers_400(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    client.post(f"/api/courses/{cid}/exams/m1")
    resp = client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": ["wrong shape"]})
    assert resp.status_code == 400
    assert (root / cid / "exams" / "m1.json").exists()  # still pending


def test_get_course_includes_exam_status(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.get(f"/api/courses/{cid}")
    body = resp.get_json()
    assert body["exams"] == {} and body["coursePassed"] is False


def _post_exam_result(client, course_id, exam_key, payload, i=0):
    r = client.post("/api/events", json={"events": [{
        "client_event_id": f"x-{exam_key}-{i}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": f"2026-07-1{i}T10:00:00+00:00",
        "course_id": course_id, "topic_id": exam_key, "payload": payload,
    }]})
    assert r.status_code == 200


def test_remediation_404_without_failed_exam(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, _ = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 404


def test_remediation_404_for_module_dropped_by_a_later_revision(tmp_path, monkeypatch):
    """A failed exam_result can outlive a manifest revision that drops its module (e.g. a
    course rewrite). The remediation gate must 404 rather than try to remediate a module
    that no longer exists, and must not create a remediation file for it."""
    client = _client(tmp_path, monkeypatch)
    manifest, _ = _fixture_course(courses, tmp_path)  # module id "m1"
    cid = manifest["id"]
    _post_exam_result(client, cid, "m9",
                      {"score": 0.0, "passed": False, "attempt": 1,
                       "weakSpots": [{"lessonId": "x", "lessonTitle": "X", "objectives": []}]})
    r = client.post(f"/api/courses/{cid}/exams/m9/remediation")
    assert r.status_code == 404
    assert not (tmp_path / cid / "remediation" / "m9.json").exists()


def test_remediation_generates_serves_and_reuses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["Calculate X"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 1, "weakSpots": weak})
    gaps = {"gaps": [{"lessonId": lesson_id, "explanationHtml": "<p>angle</p>",
                      "practice": [
                          {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                           "answer": 0, "explanation": "e"},
                          {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
                      ],
                      "apply": {"prompt": "<p>scenario</p>", "modelAnswer": "covers x"}}]}
    calls = []

    def fake_run(prompt, validate=None, **kw):
        calls.append(prompt)
        assert validate(gaps)
        return gaps

    monkeypatch.setattr(claude_client, "run_structured", fake_run)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 200
    body = r.get_json()
    assert body["attempt"] == 1 and body["gaps"][0]["lessonTitle"] == "A"
    assert (tmp_path / cid / "remediation" / "m1.json").exists()
    r2 = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r2.status_code == 200 and len(calls) == 1              # served from disk


def test_remediation_maps_claude_errors(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _post_exam_result(client, cid, "m1", {"score": 0.5, "passed": False, "attempt": 1,
        "weakSpots": [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": []}]})

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("nope")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 502
    assert not (tmp_path / cid / "remediation" / "m1.json").exists()


def _remediation_session_on_disk(root, cid, lesson_id, *, with_apply=True, attempt=1,
                                 exam_key="m1"):
    from backend import remediation
    gap = {"lessonId": lesson_id, "lessonTitle": "A", "objectives": [],
           "explanationHtml": "<p>angle</p>",
           "practice": [
               {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                "answer": 0, "explanation": "e"},
               {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
           ]}
    if with_apply:
        gap["apply"] = {"prompt": "<p>scenario</p>", "modelAnswer": "covers x"}
    session = {"examKey": exam_key, "courseId": cid, "attempt": attempt,
               "generatedAt": "2026-07-16T00:00:00+00:00", "gaps": [gap]}
    remediation.save_session(root, cid, session)
    return session


def test_remediation_grade_returns_verdict_and_model_answer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _remediation_session_on_disk(tmp_path, cid, lesson_id)
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, **kw: {"verdict": "close",
                                              "note": "Nearly <script>x</script>"})
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "my attempt"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["verdict"] == "close"
    assert "<script>" not in body["note"]                       # sanitized
    assert body["modelAnswer"] == "covers x"                    # revealed only after grading


def test_remediation_grade_statuses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # 404: no session on disk
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "a"}).status_code == 404
    _remediation_session_on_disk(tmp_path, cid, lesson_id)
    # 400: bad gapIndex shapes
    for bad in [{"gapIndex": 5, "answer": "a"}, {"gapIndex": -1, "answer": "a"},
                {"gapIndex": "0", "answer": "a"}, {"answer": "a"}]:
        assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                           json=bad).status_code == 400
    # 400: empty answer
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "  "}).status_code == 400
    # 400: non-string answer
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": 5}).status_code == 400
    # 502 on Claude failure
    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "a"}).status_code == 502
    # 503 when Claude needs reauth
    def auth_boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "a"})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"


def test_remediation_grade_rejects_non_dict_body(tmp_path, monkeypatch):
    """A forged, truthy non-dict JSON body (list, string, ...) must not survive past
    `request.get_json()` into `.get()` calls — that would raise AttributeError -> 500."""
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _remediation_session_on_disk(tmp_path, cid, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json=[1, 2]).status_code == 400
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json="oops").status_code == 400


def test_remediation_grade_400_for_legacy_gap_without_apply(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _remediation_session_on_disk(tmp_path, cid, lesson_id, with_apply=False)  # legacy Pi session
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "a"})
    assert r.status_code == 400


def test_remediation_grade_400_for_gap_with_blank_modelAnswer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # Create a session with a gap whose apply has prompt but blank modelAnswer
    from backend import remediation
    gap = {"lessonId": lesson_id, "lessonTitle": "A", "objectives": [],
           "explanationHtml": "<p>angle</p>",
           "practice": [
               {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                "answer": 0, "explanation": "e"},
           ],
           "apply": {"prompt": "<p>x</p>", "modelAnswer": "  "}}
    session = {"examKey": "m1", "courseId": cid, "attempt": 1,
               "generatedAt": "2026-07-16T00:00:00+00:00", "gaps": [gap]}
    remediation.save_session(tmp_path, cid, session)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "a"})
    assert r.status_code == 400


def test_final_locked_until_all_modules_passed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # Stub generation FIRST: if the 409 gate were broken, the route must hit this
    # stub (502), never a real Claude call. 409 vs 502 is the whole assertion.
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    r = client.post(f"/api/courses/{cid}/exams/final")
    assert r.status_code == 409
    for module in manifest["modules"]:
        _post_exam_result(client, cid, module["id"],
                          {"score": 0.9, "passed": True, "attempt": 1, "weakSpots": []}, i=1)
    r2 = client.post(f"/api/courses/{cid}/exams/final")
    assert r2.status_code == 502  # gate opened; generation stub reached


def test_transcript_route_returns_courses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, _ = _fixture_course(courses, tmp_path)
    r = client.get("/api/transcript")
    assert r.status_code == 200
    body = r.get_json()
    assert body["courses"][0]["courseId"] == manifest["id"]
    assert body["courses"][0]["final"]["passed"] is False


def _capstone_file(root, cid, scope, title):
    cap = {"scope": scope, "title": title, "intro": "i", "items": [
        {"title": "A", "detail": "d", "source": "s"},
        {"title": "B", "detail": "d", "source": "s"}]}
    p = root / cid / "capstones" / f"{scope}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap))
    return cap


def _capstone_generate():
    rubric = {"rubric": [{"criterion": f"C{i}"} for i in range(4)]}
    grade = {"perCriterion": [
        {"index": i, "met": "met", "note": "n", "evidence": "q"} for i in range(4)],
        "summary": "s"}

    def fake(prompt, *, validate=None, **kw):
        obj = grade if '"perCriterion"' in prompt else rubric
        assert validate is None or validate(obj)
        return obj
    return fake


def test_capstone_submit_grades_and_records(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")
    monkeypatch.setattr(claude_client, "run_structured", _capstone_generate())
    r = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "my project"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["score"] == 1.0 and body["passed"] is True and body["attempt"] == 1
    assert len(body["rubric"]) == 4
    assert body["perCriterion"][0]["evidence"] == "q"           # response keeps evidence
    saved = json.loads((tmp_path / cid / "capstones" / f"{mid}.json").read_text())
    assert len(saved["rubric"]) == 4                            # read-time upgrade persisted
    r2 = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "more"})
    assert r2.get_json()["attempt"] == 2                        # unlimited attempts
    ev = client.get("/api/events?type=capstone_result").get_json()["events"]
    assert len(ev) == 2
    assert "evidence" not in ev[0]["payload"]["perCriterion"][0]  # never stored


def test_capstone_submit_requires_work(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={}).status_code == 400
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "  "}).status_code == 400


def test_capstone_submit_rejects_non_string_work(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": 123}).status_code == 400
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": ["x"]}).status_code == 400


def test_capstone_submit_rejects_non_dict_body(tmp_path, monkeypatch):
    """A forged, truthy non-dict JSON body (list, string, ...) must not survive past
    `request.get_json()` into `.get()` calls — that would raise AttributeError -> 500."""
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json=[1, 2]).status_code == 400
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json="oops").status_code == 400


def test_capstone_submit_404_without_generated_capstone(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "w"}).status_code == 404
    assert client.post("/api/courses/nope/capstone/m1/submit",
                       json={"work": "w"}).status_code == 404


def test_capstone_submit_maps_claude_errors(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")

    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "w"}).status_code == 502

    def auth_boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "w"})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"


def _post_marker(client, cid, event_type, payload, i, topic_id):
    r = client.post("/api/events", json={"events": [{
        "client_event_id": f"gm-{event_type}-{i}", "session_id": "s1",
        "event_type": event_type, "occurred_at": f"2026-07-16T10:{i:02d}:00+00:00",
        "course_id": cid, "topic_id": topic_id, "payload": payload,
    }]})
    assert r.status_code == 200


def test_retake_gate_matrix(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # Stub generation FIRST: reaching it (502) proves the gate is OPEN; 409 proves CLOSED.
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)

    # 1. no prior result -> first attempts always allowed (gate open, stub reached)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502

    # 2. latest failed, gap review never generated -> 409
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["o"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 1, "weakSpots": weak}, i=1)
    r = client.post(f"/api/courses/{cid}/exams/m1")
    assert r.status_code == 409
    assert "gap review" in r.get_json()["error"]
    assert r.get_json()["code"] == "gap-review"  # frontend routes this to a "Fix the gaps" escape hatch

    # 3. session exists but is incomplete -> still 409
    _remediation_session_on_disk(tmp_path, cid, lesson_id, attempt=1)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409

    # 4. legacy events without examKey/attempt markers do not count -> still 409
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation"},
                     i, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409

    # 5. fully worked session (2 practice + 1 apply) -> gate opens (stub reached)
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation",
                      "examKey": "m1", "attempt": 1}, 10 + i, lesson_id)
    _post_marker(client, cid, "lesson_explained",
                 {"verdict": "correct", "source": "remediation", "examKey": "m1",
                  "attempt": 1, "index": 0}, 20, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502

    # 6. passed exams retake freely even with an old fail on record
    _post_exam_result(client, cid, "m1",
                      {"score": 0.9, "passed": True, "attempt": 2, "weakSpots": []}, i=2)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502


def test_retake_gate_stale_session_blocks_after_new_fail(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["o"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 2, "weakSpots": weak}, i=3)
    # session + events all belong to attempt 1: completed for 1, stale for 2
    _remediation_session_on_disk(tmp_path, cid, lesson_id, attempt=1)
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation",
                      "examKey": "m1", "attempt": 1}, 30 + i, lesson_id)
    _post_marker(client, cid, "lesson_explained",
                 {"verdict": "correct", "source": "remediation", "examKey": "m1",
                  "attempt": 1, "index": 0}, 40, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409


def test_retake_gate_full_corrective_loop_via_api(tmp_path, monkeypatch):
    """The gap-review escape hatch end to end: fail -> retake 409 (with the code the
    frontend keys "Fix the gaps" off of) -> POST remediation for real through the route
    (not written straight to disk) -> mark every practice + apply item complete via real
    event posts -> the retake reaches generation again. Proven by the stubbed-502
    technique (reaching generation proves the gate is open), same as the gate matrix."""
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)

    # 1. fail the exam
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["o"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 1, "weakSpots": weak}, i=1)

    # 2. retake 409s carrying the code the frontend routes to "Fix the gaps"
    r = client.post(f"/api/courses/{cid}/exams/m1")
    assert r.status_code == 409
    assert r.get_json()["code"] == "gap-review"

    # 3. POST remediation for real — through the route, not written to disk directly
    gaps = {"gaps": [{"lessonId": lesson_id, "explanationHtml": "<p>angle</p>",
                      "practice": [
                          {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                           "answer": 0, "explanation": "e"},
                          {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
                      ],
                      "apply": {"prompt": "<p>scenario</p>", "modelAnswer": "covers x"}}]}
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None, **kw: gaps)
    r2 = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r2.status_code == 200
    assert (tmp_path / cid / "remediation" / "m1.json").exists()

    # 4. generated but not yet worked -> still gated
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409

    # 5. insert completion marker events for the 2 practice items + the 1 apply item
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation",
                      "examKey": "m1", "attempt": 1}, i, lesson_id)
    _post_marker(client, cid, "lesson_explained",
                 {"verdict": "correct", "source": "remediation", "examKey": "m1",
                  "attempt": 1, "index": 0}, 10, lesson_id)

    # 6. retake now reaches generation -- the gate is open
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502


# ---------------------------------------------------------------------------
# fresh review items
# ---------------------------------------------------------------------------

def test_review_items_route_returns_items(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    items = {"items": [
        {"type": "mcq", "prompt": "q1", "choices": ["a", "b"], "answer": 0, "explanation": "e1"},
        {"type": "fill", "prompt": "q2", "answer": "x", "explanation": "e2"},
    ]}
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None, **kw: items)
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["items"]) == 2
    assert (root / cid / "review-items" / f"{lesson_id}.json").exists()


def test_review_items_route_reuses_cache_for_same_review_count(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake(prompt, validate=None, **kw):
        calls.append(prompt)
        return {"items": [{"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]}

    monkeypatch.setattr(claude_client, "run_structured", fake)
    r1 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    r2 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(calls) == 1  # served from disk on the second call


def test_review_items_route_review_count_from_seeded_events(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, db, events
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-1", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2026-07-10T09:00:00+00:00", "course_id": cid,
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()

    seen_prompts = []

    def fake(prompt, validate=None, **kw):
        seen_prompts.append(prompt)
        return {"items": [{"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]}

    monkeypatch.setattr(claude_client, "run_structured", fake)
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200
    stored = json.loads((root / cid / "review-items" / f"{lesson_id}.json").read_text())
    assert stored["reviewCount"] == 1        # one lesson_reviewed event seeded

    # A second review event bumps the stamp -> cache miss -> regenerates
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-2", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2026-07-11T09:00:00+00:00", "course_id": cid,
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()
    resp2 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp2.status_code == 200
    stored2 = json.loads((root / cid / "review-items" / f"{lesson_id}.json").read_text())
    assert stored2["reviewCount"] == 2
    assert len(seen_prompts) == 2


def test_review_items_route_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.get(f"/api/courses/{cid}/lessons/nope/review-items").status_code == 404
    assert client.get("/api/courses/nope/lessons/x/review-items").status_code == 404
    assert client.get(f"/api/courses/Bad_Id/lessons/{lesson_id}/review-items").status_code == 404


def test_review_items_route_does_not_require_cached_lesson_file(client, tmp_path, monkeypatch):
    """Items come from the manifest + spine, not the lesson body — deleting the cached
    lesson file must not 404 the route."""
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    (root / cid / "lessons" / f"{lesson_id}.json").unlink()
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None, **kw: {"items": [
                            {"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]})
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200


def test_review_items_route_maps_claude_errors(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items").status_code == 502

    def auth_boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"


# ---------------------------------------------------------------------------
# highlight -> review item
# ---------------------------------------------------------------------------

def test_highlight_review_item_route_creates_and_persists(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "item": {"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}})
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json={"text": "a passage worth remembering"})
    assert resp.status_code == 200
    item = resp.get_json()["item"]
    assert item["prompt"] == "q" and item["source"] == "highlight" and item["id"].startswith("hi-")
    stored = json.loads((root / cid / "review-items" / f"{lesson_id}.json").read_text())
    assert stored["userItems"] == [item]


def test_highlight_review_item_route_survives_in_the_review_flow(client, tmp_path, monkeypatch):
    """The GET review-items route must fold userItems into the served items list —
    the frontend adopts res.items as-is with no separate handling."""
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "item": {"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}})
    client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
               json={"text": "a passage worth remembering"})

    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, validate=None, **kw: {
        "items": [{"type": "mcq", "prompt": "q1", "choices": ["a", "b"], "answer": 0, "explanation": "e1"}]})
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 2
    assert any(i.get("source") == "highlight" for i in items)


def test_highlight_review_item_route_rejects_empty_and_oversized_text(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json={"text": ""}).status_code == 400
    assert client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json={"text": "   "}).status_code == 400
    assert client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json={"text": "x" * 2001}).status_code == 400
    assert client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json={}).status_code == 400


def test_highlight_review_item_route_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    body = {"text": "some passage"}
    assert client.post(f"/api/courses/{cid}/lessons/nope/highlight-review-item",
                       json=body).status_code == 404
    assert client.post("/api/courses/nope/lessons/x/highlight-review-item",
                       json=body).status_code == 404
    assert client.post(f"/api/courses/Bad_Id/lessons/{lesson_id}/highlight-review-item",
                       json=body).status_code == 404


def test_highlight_review_item_route_maps_claude_errors(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    body = {"text": "some passage"}

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item",
                       json=body).status_code == 502

    def auth_boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/highlight-review-item", json=body)
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"


def test_course_notes_route_returns_annotated_lessons_only(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace", json={"notes": "key idea here", "chat": []})
    resp = client.get(f"/api/courses/{cid}/notes")
    assert resp.status_code == 200
    lessons = resp.get_json()["lessons"]
    assert len(lessons) == 1
    assert lessons[0]["lessonId"] == lesson_id
    assert lessons[0]["notes"] == "key idea here"
    assert lessons[0]["lessonTitle"] == "Lesson One"
    assert lessons[0]["moduleTitle"] == "Module One"


def test_course_notes_route_empty_when_nothing_annotated(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    resp = client.get(f"/api/courses/{manifest['id']}/notes")
    assert resp.status_code == 200
    assert resp.get_json()["lessons"] == []


def test_course_notes_route_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    assert client.get("/api/courses/nope/notes").status_code == 404
    assert client.get("/api/courses/Bad_Id/notes").status_code == 404


def test_get_lesson_route_includes_prior_knowledge_in_prompt(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, events, db
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "PK Demo", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]

    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "pk-1", "session_id": "s1", "event_type": "prior_knowledge",
            "occurred_at": "2026-06-21T10:00:00+00:00", "course_id": cid, "topic_id": lid,
            "payload": {"text": "I think it is about gradient descent"},
        }])
    finally:
        conn.close()

    made = {"id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
            "eyebrow": "EXERCISE", "promptHtml": "<p>p</p>", "hintHtml": "h",
            "solutionAns": "a", "solutionNote": "n",
            "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}],
            "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                        "answer": 0, "explanation": "Because."},
            "spine": {"summary": "s", "concepts": [{"term": "t", "definition": "d"}]}}
    captured = {}

    def fake_sourced(prompt, **kw):
        captured["prompt"] = prompt
        return made, []
    monkeypatch.setattr(claude_client, "run_sourced", fake_sourced)
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: dict(made))

    resp = client.get(f"/api/courses/{cid}/lessons/{lid}")
    assert resp.status_code == 200
    assert "I think it is about gradient descent" in captured["prompt"]
    assert "verbatim reply" in captured["prompt"]


def test_get_lesson_route_omits_prior_knowledge_without_event(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "PK Demo 2", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]

    made = {"id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
            "eyebrow": "EXERCISE", "promptHtml": "<p>p</p>", "hintHtml": "h",
            "solutionAns": "a", "solutionNote": "n",
            "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}],
            "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                        "answer": 0, "explanation": "Because."},
            "spine": {"summary": "s", "concepts": [{"term": "t", "definition": "d"}]}}
    captured = {}

    def fake_sourced(prompt, **kw):
        captured["prompt"] = prompt
        return made, []
    monkeypatch.setattr(claude_client, "run_sourced", fake_sourced)
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: dict(made))

    resp = client.get(f"/api/courses/{cid}/lessons/{lid}")
    assert resp.status_code == 200
    assert "verbatim reply" not in captured["prompt"]


def test_deepen_endpoint_includes_prior_knowledge_in_prompt(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, events, db
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "pk-2", "session_id": "s1", "event_type": "prior_knowledge",
            "occurred_at": "2026-06-21T10:00:00+00:00", "course_id": cid, "topic_id": lesson_id,
            "payload": {"text": "I recall something about eigenvectors"},
        }])
    finally:
        conn.close()

    deeper = {"id": "x", "courseId": "x", "topic": "t", "step": 9, "totalSteps": 9,
              "eyebrow": "EXERCISE", "promptHtml": "<p>deeper now</p>", "hintHtml": "h",
              "solutionAns": "a", "solutionNote": "n",
              "checks": [{"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}],
              "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                          "answer": 0, "explanation": "Because."},
              "spine": {"summary": "s", "concepts": [{"term": "t", "definition": "d"}]}}
    captured = {}

    def fake_sourced(prompt, **kw):
        captured["prompt"] = prompt
        return deeper, []
    monkeypatch.setattr(claude_client, "run_sourced", fake_sourced)
    monkeypatch.setattr(claude_client, "run_structured", lambda prompt, **kw: dict(deeper))

    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/deepen")
    assert resp.status_code == 200
    assert "I recall something about eigenvectors" in captured["prompt"]
    assert "verbatim reply" in captured["prompt"]


def test_status_route_404_bad_id(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.get("/api/courses/Bad_Id/lessons/l1/status")
    assert resp.status_code == 404


def test_status_route_404_unknown_course(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.get("/api/courses/nope/lessons/l1/status")
    assert resp.status_code == 404


def test_status_route_404_unknown_lesson(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    resp = client.get(f"/api/courses/{cid}/lessons/nope/status")
    assert resp.status_code == 404


def test_status_route_reports_false_then_true(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "Status Demo", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]

    resp = client.get(f"/api/courses/{cid}/lessons/{lid}/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"generated": False}

    (root / cid / "lessons" / f"{lid}.json").write_text(json.dumps({
        "id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "p", "hintHtml": "h",
        "solutionAns": "a", "solutionNote": "n",
    }))
    resp2 = client.get(f"/api/courses/{cid}/lessons/{lid}/status")
    assert resp2.status_code == 200
    assert resp2.get_json() == {"generated": True}


def test_status_route_corrupt_file_reports_false(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "Corrupt Demo", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    (root / cid / "lessons" / f"{lid}.json").write_text("{not valid json")

    resp = client.get(f"/api/courses/{cid}/lessons/{lid}/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"generated": False}


# ---- teach mode ----

def test_lesson_chat_teach_mode_swaps_prompt_and_drops_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "Let me explain GET requests."}],
                             "mode": "teach"})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)  # drain the lazy SSE generator
    assert "event: done" in text
    prompt, kw = calls[0]
    assert "curious" in prompt.lower()          # teach system prompt selected
    assert not kw.get("tools")                  # WebSearch/WebFetch dropped


def test_lesson_chat_teach_mode_typo_falls_back_to_normal(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    prompts = []

    def fake_stream(prompt, **kw):
        prompts.append(prompt)
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    for mode in ("Teach", "teach ", "TEACH"):
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                           json={"messages": [{"role": "user", "content": "hi"}], "mode": mode})
        assert resp.status_code == 200
        resp.get_data(as_text=True)
    assert len(prompts) == 3
    for p in prompts:
        assert "never state the answer" in p.lower()          # default system prompt
        assert "curious" not in p.lower()      # teach system prompt absent


# ---- /teach grading route ----

def test_teach_route_grades_teaching(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    captured = {}

    def fake_run_structured(prompt, **kw):
        captured["prompt"] = prompt
        return {"verdict": "close", "note": "Good start; explain X more."}

    monkeypatch.setattr(claude_client, "run_structured", fake_run_structured)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach", json={
        "messages": [
            {"role": "user", "content": "A GET request fetches data from a server."},
            {"role": "assistant", "content": "So it can also change data?"},
        ]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["verdict"] == "close"
    assert "explain X more" in body["note"]
    prompt = captured["prompt"]
    assert '"speaker": "teacher"' in prompt
    assert '"speaker": "student"' in prompt
    assert "JSON object, no prose, no fence" in prompt


def test_teach_route_sanitizes_note(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, **kw: {"verdict": "correct", "note": "Nice <script>alert(1)</script> job"})
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach",
                       json={"messages": [{"role": "user", "content": "teaching..."}]})
    assert resp.status_code == 200
    assert "<script" not in resp.get_json()["note"]


def test_teach_route_requires_a_teacher_turn(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    for payload in (
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "hi"}]},
        {"messages": [{"role": "user", "content": "   "}]},
        {},
    ):
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "teach something first"


def test_teach_route_skips_non_dict_messages(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, **kw: {"verdict": "correct", "note": "n"})
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach",
                       json={"messages": ["nope", 5, {"role": "user", "content": "real turn"}]})
    assert resp.status_code == 200


def test_teach_route_missing_lesson_404(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    resp = client.post(f"/api/courses/{cid}/lessons/nope/teach",
                       json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 404


def test_teach_route_bad_ids_404(client):
    resp = client.post("/api/courses/Bad_Id/lessons/l1/teach", json={"messages": []})
    assert resp.status_code == 404


def test_teach_route_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach",
                       json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"


def test_teach_route_maps_claude_error_to_502(client, tmp_path, monkeypatch):
    # Simulates the exhausted-retry outcome when the model keeps returning a verdict
    # outside the trio and valid_grade rejects it every time — run_structured's own
    # retry-then-raise is already covered generically in test_claude_client.py.
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    def boom(prompt, **kw):
        raise claude_client.ClaudeError("structured generation failed after retry")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/teach",
                       json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "could not grade your teaching"


def test_course_image_route_serves_file(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-1.jpg").write_bytes(b"\xff\xd8\xffjpegdata")
    resp = client.get("/api/courses/demo/images/demo-l1-1.jpg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"
    assert resp.data == b"\xff\xd8\xffjpegdata"


def test_course_image_route_serves_webp(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-2.webp").write_bytes(b"RIFF0000WEBPdata")
    resp = client.get("/api/courses/demo/images/demo-l1-2.webp")
    assert resp.status_code == 200
    assert resp.mimetype == "image/webp"


def test_course_image_route_404s_on_bad_extension(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-1.svg").write_bytes(b"<svg></svg>")
    resp = client.get("/api/courses/demo/images/demo-l1-1.svg")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_course_image_route_404s_on_uppercase_filename(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "DEMO-L1-1.jpg").write_bytes(b"\xff\xd8\xff")
    resp = client.get("/api/courses/demo/images/DEMO-L1-1.jpg")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_course_image_route_404s_on_bad_course_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/courses/UPPER_CASE/images/demo-l1-1.jpg")
    assert resp.status_code == 404


def test_course_image_route_404s_on_path_traversal_attempt(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    # A traversal payload passed as the filename segment either fails routing
    # entirely (extra path segments) or reaches the view and fails the strict
    # filename regex — both outcomes are a 404, which is the only property
    # this test needs to prove (no traversal ever serves a file).
    resp = client.get("/api/courses/demo/images/..%2f..%2fapp.py")
    assert resp.status_code == 404
