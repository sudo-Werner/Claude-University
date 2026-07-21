import json

import pytest

from backend import claude_client, courses, jobs


@pytest.fixture(autouse=True)
def clean_registry():
    jobs.reset()
    yield
    jobs.reset()


def _write_course(root, course_id="humanbody", lesson_id="humanbody-l1"):
    cdir = root / course_id
    (cdir / "lessons").mkdir(parents=True)
    manifest = {
        "id": course_id, "title": "Human Body",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": lesson_id, "title": "Cells"},
        ]}],
    }
    (cdir / "course.json").write_text(json.dumps(manifest))
    return cdir


def _lesson_json(course_id, lesson_id):
    return {"id": lesson_id, "courseId": course_id, "topic": "Cells"}


def test_post_starts_job_and_get_polls_it(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fake_ensure(content_dir, course_id, lesson_id, prof, *, generate, **kw):
        kw["verify_generate"]("audit prompt", lambda o: True)
        (cdir / "lessons" / f"{lesson_id}.json").write_text(
            json.dumps(_lesson_json(course_id, lesson_id)))
        return _lesson_json(course_id, lesson_id)

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fake_ensure)
    monkeypatch.setattr(claude_client, "structured_generate", lambda p, v: {"ok": True})

    resp = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] in ("running", "done")

    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)

    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate?since=0")
    body = resp.get_json()
    assert body["status"] == "done"
    texts = [e["text"] for e in body["events"]]
    assert "Researching and drafting the lesson…" in texts
    assert "Fact-check audit…" in texts
    assert "Lesson saved." in texts
    assert body["next"] == len(texts)


def test_post_dedups_a_running_job(client, tmp_path, monkeypatch):
    import threading
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson",
                        lambda *a, **k: release.wait(5))

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    first = jobs.get("humanbody", "humanbody-l1")
    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert jobs.get("humanbody", "humanbody-l1") is first
    release.set()
    first.thread.join(5)


def test_post_on_cached_lesson_returns_done_without_job(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    (cdir / "lessons" / "humanbody-l1.json").write_text(
        json.dumps(_lesson_json("humanbody", "humanbody-l1")))
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "done"
    assert jobs.get("humanbody", "humanbody-l1") is None


def test_get_without_job_says_done_or_none(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.get_json()["status"] == "none"

    (cdir / "lessons" / "humanbody-l1.json").write_text(
        json.dumps(_lesson_json("humanbody", "humanbody-l1")))
    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.get_json()["status"] == "done"


def test_auth_failure_surfaces_reauth_message(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fail(*a, **k):
        raise claude_client.ClaudeAuthError("expired")

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fail)

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)
    body = client.get(
        "/api/courses/humanbody/lessons/humanbody-l1/generate").get_json()
    assert body["status"] == "error"
    assert "re-authentication" in body["error"]


def test_timeout_failure_says_took_too_long(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fail(*a, **k):
        raise claude_client.ClaudeError("claude stream timed out after 1200s")

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fail)

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)
    body = client.get(
        "/api/courses/humanbody/lessons/humanbody-l1/generate").get_json()
    assert body["status"] == "error"
    assert "too long" in body["error"]


def test_unknown_ids_404(client):
    assert client.post("/api/courses/nope/lessons/x/generate").status_code == 404
    assert client.get("/api/courses/nope/lessons/x/generate").status_code == 404


def test_post_returns_409_when_a_different_lesson_is_generating(client, tmp_path, monkeypatch):
    import threading
    root = tmp_path / "content"
    _write_course(root, course_id="humanbody", lesson_id="humanbody-l1")
    _write_course(root, course_id="chemistry", lesson_id="chem-l1")
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", lambda *a, **k: release.wait(5))

    resp1 = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp1.status_code == 202

    resp2 = client.post("/api/courses/chemistry/lessons/chem-l1/generate")
    assert resp2.status_code == 409
    assert "already generating" in resp2.get_json()["error"]
    assert jobs.get("chemistry", "chem-l1") is None  # the second lesson never started

    release.set()
    jobs.get("humanbody", "humanbody-l1").thread.join(5)


def test_post_same_lesson_still_joins_while_running(client, tmp_path, monkeypatch):
    import threading
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", lambda *a, **k: release.wait(5))

    resp1 = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp1.status_code == 202
    first = jobs.get("humanbody", "humanbody-l1")

    resp2 = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp2.status_code == 202
    assert jobs.get("humanbody", "humanbody-l1") is first

    release.set()
    first.thread.join(5)


def test_run_wrapper_reports_error_when_lesson_vanishes_mid_generation(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", lambda *a, **k: None)

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)

    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate")
    body = resp.get_json()
    assert body["status"] == "error"
    texts = [e["text"] for e in body["events"]]
    assert "Lesson saved." not in texts


def test_generation_jobs_lists_running_only(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    import threading
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson",
                        lambda *a, **k: release.wait(5))

    assert client.get("/api/generation-jobs").get_json() == {"jobs": []}
    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    body = client.get("/api/generation-jobs").get_json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["courseId"] == "humanbody"
    assert body["jobs"][0]["lessonId"] == "humanbody-l1"
    assert body["jobs"][0]["status"] == "running"
    release.set()
    jobs.get("humanbody", "humanbody-l1").thread.join(5)
