import json

import pytest

from backend import app as app_module, courses, quiz


@pytest.fixture()
def client(tmp_path):
    app = app_module.create_app(db_path=str(tmp_path / "t.db"))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _seed_course(monkeypatch, tmp_path, *, completed=("c-l1",)):
    root = tmp_path / "courses"
    (root / "c" / "lessons").mkdir(parents=True)
    (root / "c" / "course.json").write_text(json.dumps({
        "id": "c", "title": "Course", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "c-l1", "title": "L1"}, {"id": "c-l2", "title": "L2"}]}],
    }))
    for lid in completed:
        (root / "c" / "lessons" / f"{lid}.json").write_text(json.dumps({"id": lid}))
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    return root


def _complete_lesson(client, lesson_id, course_id="c"):
    client.post("/api/events", json={"events": [{
        "client_event_id": f"done-{lesson_id}", "session_id": "s1",
        "event_type": "lesson_completed", "occurred_at": "2026-07-01T10:00:00+00:00",
        "course_id": course_id, "topic_id": lesson_id,
    }]})


# ---- GET /quiz/round ----

def test_get_round_locked_when_pool_empty(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path, completed=())
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: None)
    resp = client.get("/api/courses/c/quiz/round")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "locked"}


def test_get_round_generating_when_bank_empty_and_pool_nonempty(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    # Patch BEFORE completing the lesson: /api/events itself nudges restock
    # (Task 7's other behavior) for any lesson_completed event, so patching
    # after would let one real, un-patched kick_restock call slip through.
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: None)
    _complete_lesson(client, "c-l1")
    calls = []
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: calls.append((a, k)))
    resp = client.get("/api/courses/c/quiz/round")
    assert resp.get_json() == {"status": "generating"}
    assert len(calls) == 1


def test_get_round_ready_serves_banked_round(client, tmp_path, monkeypatch):
    root = _seed_course(monkeypatch, tmp_path)
    # Patch BEFORE completing the lesson — see the comment in
    # test_get_round_generating_when_bank_empty_and_pool_nonempty above.
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: None)
    _complete_lesson(client, "c-l1")
    quiz.save_round(root, "c", {"round_id": "round-000000000001", "course_id": "c",
                                "format": "rapid_fire", "title": "T", "host_intro": "I",
                                "questions": [], "created_at": "2026-07-01T00:00:00+00:00"})
    resp = client.get("/api/courses/c/quiz/round")
    body = resp.get_json()
    assert body["status"] == "ready"
    assert body["round"]["round_id"] == "round-000000000001"


def test_get_round_404_for_unknown_course(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    resp = client.get("/api/courses/nope/quiz/round")
    assert resp.status_code == 404


def test_get_round_bad_course_id_404(client):
    resp = client.get("/api/courses/Bad_Id/quiz/round")
    assert resp.status_code == 404


# ---- POST /quiz/results ----

def test_post_results_inserts_event_and_kicks_restock(client, tmp_path, monkeypatch):
    root = _seed_course(monkeypatch, tmp_path)
    quiz.save_round(root, "c", {"round_id": "round-000000000001", "course_id": "c",
                                "format": "rapid_fire", "title": "T", "host_intro": "I",
                                "questions": [], "created_at": "2026-07-01T00:00:00+00:00"})
    calls = []
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: calls.append((a, k)))
    resp = client.post("/api/courses/c/quiz/results", json={
        "client_event_id": "ce1", "session_id": "s1", "round_id": "round-000000000001",
        "format": "rapid_fire", "score": 6, "total": 8, "missed": {"c-l1": 1},
    })
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert len(calls) == 1
    assert quiz.bank_count(root, "c") == 0


def test_post_results_400_on_malformed_body(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    resp = client.post("/api/courses/c/quiz/results", json={"client_event_id": "", "session_id": "s1"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_post_results_bad_course_id_404(client):
    resp = client.post("/api/courses/Bad_Id/quiz/results", json={})
    assert resp.status_code == 404


# ---- GET /quiz/stats ----

def test_get_stats_returns_computed_stats(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    client.post("/api/events", json={"events": [{
        "client_event_id": "qr1", "session_id": "s1", "event_type": "quiz_round",
        "occurred_at": "2026-07-01T00:00:00+00:00", "course_id": "c", "topic_id": "round-x",
        "payload": {"format": "rapid_fire", "score": 4, "total": 8, "missed": {}},
    }]})
    resp = client.get("/api/courses/c/quiz/stats")
    body = resp.get_json()
    assert body["roundsPlayed"] == 1
    assert body["bestPct"] == 50


def test_get_stats_bad_course_id_404(client):
    resp = client.get("/api/courses/Bad_Id/quiz/stats")
    assert resp.status_code == 404


# ---- lesson_completed nudges restock ----

def test_lesson_completed_event_nudges_restock(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: calls.append(a[2]))
    client.post("/api/events", json={"events": [{
        "client_event_id": "done-c-l1", "session_id": "s1", "event_type": "lesson_completed",
        "occurred_at": "2026-07-01T00:00:00+00:00", "course_id": "c", "topic_id": "c-l1",
    }]})
    assert calls == ["c"]


def test_non_lesson_completed_events_do_not_nudge_restock(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: calls.append(a))
    client.post("/api/events", json={"events": [{
        "client_event_id": "ev1", "session_id": "s1", "event_type": "lesson_view",
        "occurred_at": "2026-07-01T00:00:00+00:00", "course_id": "c", "topic_id": "c-l1",
    }]})
    assert calls == []


def test_lesson_completed_dedupes_restock_nudge_per_course_in_one_batch(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: calls.append(a[2]))
    client.post("/api/events", json={"events": [
        {"client_event_id": "d1", "session_id": "s1", "event_type": "lesson_completed",
         "occurred_at": "2026-07-01T00:00:00+00:00", "course_id": "c", "topic_id": "c-l1"},
        {"client_event_id": "d2", "session_id": "s1", "event_type": "lesson_completed",
         "occurred_at": "2026-07-01T00:00:01+00:00", "course_id": "c", "topic_id": "c-l2"},
    ]})
    assert calls == ["c"]


def test_events_route_still_works_when_nudge_raises(client, tmp_path, monkeypatch):
    _seed_course(monkeypatch, tmp_path)
    monkeypatch.setattr(quiz, "kick_restock", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    resp = client.post("/api/events", json={"events": [{
        "client_event_id": "done-c-l1", "session_id": "s1", "event_type": "lesson_completed",
        "occurred_at": "2026-07-01T00:00:00+00:00", "course_id": "c", "topic_id": "c-l1",
    }]})
    assert resp.status_code == 200
    assert resp.get_json() == {"accepted": 1, "duplicates": 0}
