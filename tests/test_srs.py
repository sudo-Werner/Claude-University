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
