import json

from backend import db, events, transcript


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _course(tmp_path, cid="demo"):
    root = tmp_path / "courses"
    (root / cid / "lessons").mkdir(parents=True)
    (root / cid / "course.json").write_text(json.dumps({
        "id": cid, "title": "Demo", "subtitle": "", "brief": "b",
        "modules": [
            {"id": "m1", "title": "M1", "lessons": [{"id": f"{cid}-l1", "title": "L1"}]},
            {"id": "m2", "title": "M2", "lessons": [{"id": f"{cid}-l2", "title": "L2"}]},
        ],
    }))
    return root


def _result(conn, cid, key, score, passed, occurred, i=0):
    events.insert_events(conn, [{
        "client_event_id": f"t-{key}-{occurred}-{i}", "session_id": "s",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": cid, "topic_id": key,
        "payload": {"score": score, "passed": passed, "attempt": i + 1,
                    "perQuestion": [], "weakSpots": []},
    }])


def test_course_record_assembles_scores_attempts_and_dates(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _result(conn, "demo", "m1", 0.6, False, "2026-07-10T09:00:00+00:00", 0)
    _result(conn, "demo", "m1", 0.9, True, "2026-07-11T09:00:00+00:00", 1)
    rec = transcript.course_record(conn, root, "demo", manifest)
    m1 = rec["modules"][0]
    assert m1["attempts"] == 2 and m1["bestScore"] == 0.9 and m1["passed"]
    assert m1["passedOn"] == "2026-07-11"
    assert rec["modules"][1]["attempts"] == 0 and not rec["modules"][1]["passed"]
    assert rec["final"]["title"] == "Final exam"
    assert not rec["coursePassed"] and rec["passedOn"] is None
    assert rec["lessonsTotal"] == 2 and rec["lessonsCompleted"] == 0


def test_course_record_passed_on_is_latest_first_pass(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _result(conn, "demo", "m1", 0.9, True, "2026-07-10T09:00:00+00:00", 0)
    _result(conn, "demo", "m2", 0.85, True, "2026-07-11T09:00:00+00:00", 0)
    _result(conn, "demo", "final", 0.88, True, "2026-07-12T09:00:00+00:00", 0)
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert rec["coursePassed"] and rec["passedOn"] == "2026-07-12"


def test_course_record_carries_level_and_target_hours(tmp_path):
    conn = _conn()
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "b",
        "level": {"label": "Master-equivalent", "code": "M"}, "targetHours": 130,
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    manifest = json.loads((root / "demo" / "course.json").read_text())
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert rec["level"] == "Master-equivalent"
    assert rec["targetHours"] == 130


def test_course_record_falls_back_to_level_code_when_no_label(tmp_path):
    conn = _conn()
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "b",
        "level": {"code": "M"},
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    manifest = json.loads((root / "demo" / "course.json").read_text())
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert rec["level"] == "M"


def test_course_record_level_and_target_hours_none_for_legacy_manifest(tmp_path):
    # A legacy course.json predates the level/targetHours fields entirely.
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    assert "level" not in manifest and "targetHours" not in manifest
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert rec["level"] is None
    assert rec["targetHours"] is None


def test_transcript_lists_courses_and_skips_malformed(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    (root / "broken").mkdir()
    (root / "broken" / "course.json").write_text("{nope")
    out = transcript.transcript(conn, root)
    assert [c["courseId"] for c in out] == ["demo"]
