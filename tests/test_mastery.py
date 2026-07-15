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


# --- sub-project D: widened accuracy pool ---

def _completed(conn, lesson):
    _ev(conn, "lesson_completed", lesson, {}, "2026-07-10T10:00:00+00:00")


def _exam_ev(conn, exam_key, per_question, occurred="2026-07-12T10:00:00+00:00"):
    payload = {"score": 0.5, "passed": False, "attempt": 1,
               "perQuestion": per_question, "weakSpots": []}
    _ev(conn, "exam_result", exam_key, payload, occurred)


def test_explain_verdicts_join_accuracy_pool(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    _completed(conn, "demo-l1")
    # one wrong check (0/1) + one correct explain (1/1) -> acc 0.5, capped proficient
    _ev(conn, "lesson_check", "demo-l1", {"correct": False}, "2026-07-11T10:00:00+00:00")
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "correct"}, "2026-07-11T10:05:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 2.0)


def test_explain_close_is_half_and_unknown_verdict_ignored(tmp_path):
    conn = _conn()
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "close"}, "2026-07-11T10:00:00+00:00")
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "banana"}, "2026-07-11T10:01:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (0.5, 1.0)


def test_exam_questions_count_double(tmp_path):
    conn = _conn()
    # one correct check (1/1) + one 0-point exam question at weight 2 -> 1.0/3.0
    _ev(conn, "lesson_check", "demo-l1", {"correct": True}, "2026-07-11T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}])
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 3.0)


def test_exam_partial_points_scale_by_weight(tmp_path):
    conn = _conn()
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.5}])
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 2.0)  # 0.5 * EXAM_WEIGHT / EXAM_WEIGHT


def test_prequiz_never_counts(tmp_path):
    conn = _conn()
    _ev(conn, "prequiz_attempt", "demo-l1", {"correct": False, "type": "mcq"},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo") == {}


def test_remediation_checks_count_like_checks(tmp_path):
    conn = _conn()
    _ev(conn, "lesson_check", "demo-l1", {"correct": True, "source": "remediation"},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo")["demo-l1"] == (1.0, 1.0)


def test_exam_evidence_caps_mastery_level(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    _completed(conn, "demo-l1")
    # three good reviews would be "mastered"; an all-wrong exam drags acc to 0 -> attempted
    for d in ("2026-07-01", "2026-07-02", "2026-07-08"):
        _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, f"{d}T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}])
    assert mastery.lesson_mastery(conn, root, "demo")["demo-l1"] == "attempted"


def test_malformed_exam_payload_rows_are_skipped(tmp_path):
    conn = _conn()
    _ev(conn, "exam_result", "m1", {"perQuestion": [{"lessonId": "demo-l1", "points": "x"},
                                                    "junk", {"points": 1.0}]},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo") == {}


# --- Bloom's mastery-learning rule: latest exam attempt replaces the old one ---

def test_fail_then_pass_same_exam_key_counts_only_the_pass(tmp_path):
    conn = _conn()
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}],
             occurred="2026-07-11T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 1.0}],
             occurred="2026-07-12T10:00:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (2.0, 2.0)


def test_two_different_exam_keys_both_contribute_their_latest(tmp_path):
    conn = _conn()
    # module exam m1: fail then pass -> only the pass counts
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}],
             occurred="2026-07-11T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 1.0}],
             occurred="2026-07-12T10:00:00+00:00")
    # final exam: single attempt, also touches demo-l1
    _exam_ev(conn, "final", [{"lessonId": "demo-l1", "points": 0.5}],
             occurred="2026-07-13T10:00:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    # m1 pass contributes (2.0, 2.0); final contributes (1.0, 2.0) -> combined (3.0, 4.0)
    assert pool["demo-l1"] == (3.0, 4.0)


def test_performance_summary_recovers_after_fail_then_pass(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    _completed(conn, "demo-l1")
    # three good reviews would be "mastered"; a stale failed exam must not cap it anymore
    # once a later attempt on the same exam key passed cleanly.
    for d in ("2026-07-01", "2026-07-02", "2026-07-08"):
        _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, f"{d}T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}],
             occurred="2026-07-09T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 1.0}],
             occurred="2026-07-10T10:00:00+00:00")
    assert mastery.lesson_mastery(conn, root, "demo")["demo-l1"] == "mastered"
