import datetime
import json

from backend import events, stats


def _ev(i, event_type, occurred_at, course_id="c1", topic_id="c1-l1"):
    return {
        "client_event_id": f"e{i}",
        "session_id": "s1",
        "event_type": event_type,
        "occurred_at": occurred_at,
        "course_id": course_id,
        "topic_id": topic_id,
    }


TODAY = datetime.date(2026, 7, 15)


def test_streak_zero_with_no_events(conn):
    assert stats.streak_days(conn, today=TODAY) == 0


def test_streak_one_for_study_today(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-15T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_streak_alive_if_last_study_was_yesterday(conn):
    events.insert_events(conn, [_ev(1, "lesson_reviewed", "2026-07-14T21:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_streak_dead_if_last_study_two_days_ago(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-13T21:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 0


def test_streak_counts_consecutive_days(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-13T10:00:00+00:00"),
        _ev(2, "lesson_reviewed", "2026-07-14T10:00:00+00:00"),
        _ev(3, "lesson_view", "2026-07-15T10:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 3


def test_streak_stops_at_gap(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-11T10:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-12T10:00:00+00:00"),
        # 2026-07-13 missed
        _ev(3, "lesson_view", "2026-07-14T10:00:00+00:00"),
        _ev(4, "lesson_view", "2026-07-15T10:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 2


def test_multiple_events_same_day_count_once(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-15T11:00:00+00:00"),
        _ev(3, "lesson_reviewed", "2026-07-15T12:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_non_study_events_do_not_count(conn):
    events.insert_events(conn, [
        _ev(1, "session_start", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_check", "2026-07-15T09:05:00+00:00"),
        _ev(3, "hint_revealed", "2026-07-15T09:06:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 0


def _write_course(tmp_path):
    course = {
        "id": "c1",
        "title": "Machine Learning",
        "modules": [
            {"id": "m1", "title": "Foundations", "lessons": [
                {"id": "c1-l1", "title": "What is learning?"},
            ]},
        ],
    }
    d = tmp_path / "c1"
    d.mkdir(parents=True)
    (d / "course.json").write_text(json.dumps(course))
    return tmp_path


def test_activity_newest_first_with_resolved_titles(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-14T10:00:00+00:00"),
        _ev(2, "lesson_reviewed", "2026-07-15T10:00:00+00:00"),
    ])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e2'",
        (json.dumps({"quality": "good"}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert [e["type"] for e in out] == ["lesson_reviewed", "lesson_view"]
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] == "What is learning?"
    assert out[0]["quality"] == "good"
    assert out[1]["quality"] is None


def test_activity_excludes_noise_event_types(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "session_start", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_check", "2026-07-15T09:05:00+00:00"),
        _ev(3, "lesson_view", "2026-07-15T09:10:00+00:00"),
    ])
    out = stats.recent_activity(conn, content, limit=10)
    assert [e["type"] for e in out] == ["lesson_view"]


def test_activity_respects_limit(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(i, "lesson_view", f"2026-07-15T0{i}:00:00+00:00") for i in range(1, 6)
    ])
    out = stats.recent_activity(conn, content, limit=3)
    assert len(out) == 3
    assert out[0]["occurredAt"].startswith("2026-07-15T05")


def test_activity_skips_deleted_courses(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-15T10:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-15T11:00:00+00:00",
            course_id="deleted-course", topic_id="deleted-course-l9"),
    ])
    out = stats.recent_activity(conn, content, limit=10)
    assert [e["courseTitle"] for e in out] == ["Machine Learning"]


def test_activity_course_created_has_no_lesson(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "course_created", "2026-07-15T10:00:00+00:00", topic_id=None),
    ])
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "course_created"
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] is None
