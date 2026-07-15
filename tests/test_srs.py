import datetime
import json
from backend import srs, courses, events

D = datetime.date


def _rev(q, d):
    return {"quality": q, "date": d}


def test_sm2_first_good_schedules_one_day():
    s = srs.sm2([_rev("good", D(2026, 1, 1))])
    assert s["interval_days"] == 1
    assert s["repetitions"] == 1
    assert s["next_review"] == D(2026, 1, 2)


def test_sm2_progresses_1_6_then_ef():
    revs = [_rev("good", D(2026, 1, 1)), _rev("good", D(2026, 1, 2)), _rev("good", D(2026, 1, 8))]
    s = srs.sm2(revs)
    # reps: 1 (I=1), 2 (I=6), 3 (I=round(6*2.5)=15)
    assert s["repetitions"] == 3
    assert s["interval_days"] == 15
    assert s["next_review"] == D(2026, 1, 23)


def test_sm2_again_resets_and_due_same_day():
    revs = [_rev("good", D(2026, 1, 1)), _rev("good", D(2026, 1, 2)), _rev("again", D(2026, 1, 8))]
    s = srs.sm2(revs)
    assert s["repetitions"] == 0
    assert s["interval_days"] == 0
    assert s["next_review"] == D(2026, 1, 8)  # due today
    assert s["ease_factor"] < 2.5  # a fail lowers ease


def test_sm2_easy_raises_ease():
    s = srs.sm2([_rev("easy", D(2026, 1, 1))])
    assert s["ease_factor"] > 2.5


def _fixture(tmp_path):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "demo-l1", "title": "L1"}, {"id": "demo-l2", "title": "L2"}]}],
    }))
    return root


def _review_event(cid, lid, quality, when):
    return {
        "client_event_id": f"{lid}-{when}", "session_id": "s1",
        "event_type": "lesson_reviewed", "occurred_at": when,
        "course_id": cid, "topic_id": lid, "payload": {"quality": quality},
    }


def test_due_lesson_ids_reflects_schedule(conn, tmp_path):
    root = _fixture(tmp_path)
    # l1 reviewed 'good' yesterday -> due in 1 day -> due today; l2 never reviewed -> not due
    events.insert_events(conn, [_review_event("demo", "demo-l1", "good", "2026-01-01T09:00:00+00:00")])
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 1, 2))
    assert due == ["demo-l1"]
    assert srs.reviews_due_count(conn, root, "demo", today=D(2026, 1, 2)) == 1
    # before the due date, nothing is due
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 1, 1)) == []


def _exam_fail(conn, exam_key, weak_lessons, occurred):
    events.insert_events(conn, [{
        "client_event_id": f"exam-{exam_key}-{occurred}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "demo", "topic_id": exam_key,
        "payload": {"score": 0.5, "passed": False, "attempt": 1,
                    "weakSpots": [{"lessonId": l, "lessonTitle": l, "objectives": []}
                                  for l in weak_lessons]},
    }])


def _exam_pass(conn, exam_key, occurred):
    events.insert_events(conn, [{
        "client_event_id": f"examp-{exam_key}-{occurred}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "demo", "topic_id": exam_key,
        "payload": {"score": 0.9, "passed": True, "attempt": 2, "weakSpots": []},
    }])


def test_weak_spot_makes_unreviewed_lesson_due(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-14T10:00:00+00:00")
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15))
    assert due == ["demo-l1"]


def test_review_after_fail_clears_weak_spot(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-10T10:00:00+00:00")
    events.insert_events(conn, [{
        "client_event_id": "r1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-07-12T10:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    # SM-2 next_review = 07-13 which is <= today, so it IS due via SM-2; use a
    # today inside the interval to isolate the weak-spot rule.
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 12))
    assert "demo-l1" not in due


def test_later_pass_clears_weak_spot(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-10T10:00:00+00:00")
    _exam_pass(conn, "m1", "2026-07-14T10:00:00+00:00")
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15)) == []


def test_final_weak_spots_also_count(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "final", ["demo-l2"], "2026-07-14T10:00:00+00:00")
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15)) == ["demo-l2"]


def test_reviews_by_lesson_tolerates_forged_list_payload_and_bad_date(conn, tmp_path):
    root = _fixture(tmp_path)
    events.insert_events(conn, [{
        "client_event_id": "forged1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "yesterday", "course_id": "demo", "topic_id": "demo-l1",
        "payload": ["bad", "shape"],
    }])
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15))  # must not raise
    assert due == []  # forged row skipped (unparseable occurred_at)


def test_review_earlier_then_fail_later_same_day_is_due(conn, tmp_path):
    root = _fixture(tmp_path)
    events.insert_events(conn, [{
        "client_event_id": "r1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-07-15T08:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-15T10:00:00+00:00")
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15))
    assert "demo-l1" in due


def test_fail_then_review_same_day_not_due(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-15T08:00:00+00:00")
    events.insert_events(conn, [{
        "client_event_id": "r2", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-07-15T10:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15))
    assert "demo-l1" not in due
