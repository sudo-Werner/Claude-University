import json

from backend import db, mastery


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _course(tmp_path):
    import json as _j
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    manifest = {
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "Demo brief.",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "demo-l1", "title": "L1"}, {"id": "demo-l2", "title": "L2"},
        ]}],
    }
    (root / "demo" / "course.json").write_text(_j.dumps(manifest))
    return root


def _ev(conn, etype, lesson, payload, occurred):
    conn.execute(
        "INSERT INTO events (client_event_id, session_id, device, topic_id, course_id, "
        "event_type, occurred_at, received_at, payload) VALUES (?,?,?,?,?,?,?,?,?)",
        (f"{etype}-{lesson}-{occurred}", "s1", "web", lesson, "demo", etype,
         occurred, occurred, json.dumps(payload)),
    )
    conn.commit()


def test_level_for_reps_ladder():
    assert mastery.level_for(0, None) == "attempted"
    assert mastery.level_for(1, None) == "familiar"
    assert mastery.level_for(2, None) == "proficient"
    assert mastery.level_for(3, None) == "mastered"
    assert mastery.level_for(7, None) == "mastered"


def test_level_for_accuracy_gate():
    # strong recall but weak checks -> capped
    assert mastery.level_for(3, 0.4) == "attempted"   # acc<0.5 caps at attempted
    assert mastery.level_for(3, 0.6) == "proficient"  # acc<0.8 caps at proficient
    assert mastery.level_for(3, 0.9) == "mastered"    # acc>=0.8 no cap
    assert mastery.level_for(1, 0.9) == "familiar"    # gate never promotes


def test_lesson_mastery_completed_only_and_reps():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    # l1: two good reviews -> reps 2 -> proficient (no checks)
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-05T10:00:00Z")
    # l2: never completed -> absent
    m = mastery.lesson_mastery(conn, root, "demo")
    assert m == {"demo-l1": "proficient"}


def test_lesson_mastery_check_accuracy_caps():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-05T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-20T10:00:00Z")
    # reps would be 3 (mastered) but checks are 1/3 correct -> acc 0.33 -> attempted
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": True}, "2026-06-20T10:01:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 1, "type": "mcq", "correct": False}, "2026-06-20T10:02:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 2, "type": "fill", "correct": False}, "2026-06-20T10:03:00Z")
    m = mastery.lesson_mastery(conn, root, "demo")
    assert m == {"demo-l1": "attempted"}


def test_mastery_counts():
    counts = mastery.mastery_counts({"a": "mastered", "b": "mastered", "c": "familiar"})
    assert counts == {"attempted": 0, "familiar": 1, "proficient": 0, "mastered": 2}


def test_performance_summary_no_history_empty():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    assert mastery.performance_summary(conn, root, "demo") == ""


def test_performance_summary_struggling():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "again"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": False}, "2026-06-01T10:01:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 1, "type": "mcq", "correct": False}, "2026-06-01T10:02:00Z")
    s = mastery.performance_summary(conn, root, "demo")
    assert "struggling" in s.lower()


def test_performance_summary_strong():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    for d in ("2026-06-01", "2026-06-05", "2026-06-20"):
        _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "easy"}, f"{d}T10:00:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": True}, "2026-06-20T10:01:00Z")
    s = mastery.performance_summary(conn, root, "demo")
    assert "strongly" in s.lower()
