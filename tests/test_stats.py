import datetime
import json

from backend import events, stats


def _ev(i, event_type, occurred_at, course_id="c1", topic_id="c1-l1", payload=None):
    ev = {
        "client_event_id": f"e{i}",
        "session_id": "s1",
        "event_type": event_type,
        "occurred_at": occurred_at,
        "course_id": course_id,
        "topic_id": topic_id,
    }
    if payload is not None:
        ev["payload"] = payload
    return ev


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


def test_exam_and_prequiz_and_remediation_count_toward_streak(conn):
    events.insert_events(conn, [_ev(1, "exam_result", "2026-07-15T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1
    events.insert_events(conn, [_ev(2, "prequiz_attempt", "2026-07-14T09:00:00+00:00")])
    events.insert_events(conn, [_ev(3, "remediation_started", "2026-07-13T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 3


def test_activity_tolerates_forged_string_payload(conn, tmp_path):
    content = _write_course(tmp_path)
    ev = _ev(1, "lesson_view", "2026-07-15T09:00:00+00:00")
    ev["payload"] = "not-a-dict"
    events.insert_events(conn, [ev])
    out = stats.recent_activity(conn, content, limit=10)  # must not raise
    assert len(out) == 1
    assert out[0]["quality"] is None


def test_activity_labels_exam_results(conn, tmp_path):
    root = tmp_path / "courses"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "course.json").write_text(json.dumps({
        "id": "c1", "title": "Algo", "modules": [
            {"id": "m1", "title": "Sorting", "lessons": [{"id": "c1-l1", "title": "L1"}]}],
    }))
    ev = _ev(1, "exam_result", "2026-07-15T09:00:00+00:00", topic_id="m1")
    ev["payload"] = {"score": 0.85, "passed": True, "attempt": 1}
    fv = _ev(2, "exam_result", "2026-07-15T10:00:00+00:00", topic_id="final")
    fv["payload"] = {"score": 0.7, "passed": False, "attempt": 1}
    rv = _ev(3, "remediation_started", "2026-07-15T11:00:00+00:00", topic_id="final")
    events.insert_events(conn, [ev, fv, rv])
    entries = stats.recent_activity(conn, root)
    assert entries[0]["examLabel"] == "Final exam"          # remediation_started
    assert entries[1]["examLabel"] == "Final exam"
    assert entries[1]["score"] == 0.7 and entries[1]["passed"] is False
    assert entries[2]["examLabel"] == "Sorting exam"
    assert entries[2]["passed"] is True


def test_capstone_result_counts_toward_streak(conn):
    events.insert_events(conn, [_ev(1, "capstone_result", "2026-07-15T09:00:00+00:00",
                                    topic_id="m1")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_activity_labels_capstone_results(conn, tmp_path):
    root = tmp_path / "courses"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "course.json").write_text(json.dumps({
        "id": "c1", "title": "Algo", "modules": [
            {"id": "m1", "title": "Sorting", "lessons": [{"id": "c1-l1", "title": "L1"}]}],
    }))
    ev = _ev(1, "capstone_result", "2026-07-15T09:00:00+00:00", topic_id="m1")
    ev["payload"] = {"scope": "m1", "score": 0.75, "passed": True, "attempt": 1}
    cv = _ev(2, "capstone_result", "2026-07-15T10:00:00+00:00", topic_id="course")
    cv["payload"] = {"scope": "course", "score": 0.5, "passed": False, "attempt": 1}
    events.insert_events(conn, [ev, cv])
    entries = stats.recent_activity(conn, root)
    assert entries[0]["examLabel"] == "Course capstone"
    assert entries[0]["score"] == 0.5 and entries[0]["passed"] is False
    assert entries[1]["examLabel"] == "Sorting capstone"
    assert entries[1]["passed"] is True


def test_streak_counts_an_arcade_only_day(conn):
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T09:00:00+00:00", topic_id="r-abc123")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_activity_includes_quiz_round_with_score(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T10:00:00+00:00", topic_id="r-abc123")])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e1'",
        (json.dumps({"format": "rapid_fire", "score": 7, "total": 8, "missed": {}}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "quiz_round"
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] is None
    assert out[0]["score"] == 7 and out[0]["total"] == 8


def test_activity_quiz_round_tolerates_malformed_payload(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T10:00:00+00:00", topic_id="r-abc123")])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e1'",
        (json.dumps({"score": "seven", "total": 0}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "quiz_round"
    assert "score" not in out[0] or out[0]["score"] is None


def test_heatmap_past_counts_study_events_per_day(conn, tmp_path):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-13T10:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-13T14:00:00+00:00"),
        _ev(3, "lesson_reviewed", "2026-07-14T10:00:00+00:00"),
    ])
    result = stats.heatmap(conn, tmp_path, today=TODAY)
    assert result["past"]["2026-07-13"] == 2
    assert result["past"]["2026-07-14"] == 1
    assert "2026-07-15" not in result["past"]


def test_heatmap_past_ignores_non_study_events(conn, tmp_path):
    events.insert_events(conn, [_ev(1, "lesson_check", "2026-07-14T10:00:00+00:00")])
    result = stats.heatmap(conn, tmp_path, today=TODAY)
    assert result["past"] == {}


def test_heatmap_past_excludes_events_older_than_the_window(conn, tmp_path):
    old = (TODAY - datetime.timedelta(days=400)).isoformat()
    events.insert_events(conn, [_ev(1, "lesson_view", f"{old}T10:00:00+00:00")])
    result = stats.heatmap(conn, tmp_path, today=TODAY)
    assert result["past"] == {}


def test_heatmap_forecast_buckets_by_sm2_next_review_date(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "lesson_reviewed", "2026-07-15T10:00:00+00:00",
            payload={"quality": "good"}),
    ])
    result = stats.heatmap(conn, content, today=TODAY)
    # first "good" review on 2026-07-15 -> sm2 interval=1 -> next_review 2026-07-16
    assert result["forecast"] == {"2026-07-16": 1}


def test_heatmap_forecast_empty_for_never_reviewed_lessons(conn, tmp_path):
    content = _write_course(tmp_path)
    result = stats.heatmap(conn, content, today=TODAY)
    assert result["forecast"] == {}


def test_heatmap_forecast_ignores_deleted_courses(conn, tmp_path):
    events.insert_events(conn, [
        _ev(1, "lesson_reviewed", "2026-07-15T10:00:00+00:00", course_id="ghost",
            topic_id="ghost-l1", payload={"quality": "good"}),
    ])
    result = stats.heatmap(conn, tmp_path, today=TODAY)
    assert result["forecast"] == {}


def test_weekly_streak_zero_with_no_events(conn):
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 0


def test_weekly_streak_one_for_study_this_week(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-14T09:00:00+00:00")])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 1


def test_weekly_streak_alive_if_last_study_was_last_week(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-06T09:00:00+00:00")])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 1


def test_weekly_streak_dead_if_last_study_two_weeks_ago(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-06-29T09:00:00+00:00")])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 0


def test_weekly_streak_counts_consecutive_weeks(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-06-29T09:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-06T09:00:00+00:00"),
        _ev(3, "lesson_view", "2026-07-15T09:00:00+00:00"),
    ])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 3


def test_weekly_streak_stops_at_gap_week(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-06-22T09:00:00+00:00"),
        _ev(2, "lesson_view", "2026-06-29T09:00:00+00:00"),
        # week of 2026-07-06 missed
        _ev(3, "lesson_view", "2026-07-15T09:00:00+00:00"),
    ])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 1


def test_weekly_streak_multiple_events_same_week_count_once(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-13T09:00:00+00:00"),   # Monday, week start
        _ev(2, "lesson_reviewed", "2026-07-15T09:00:00+00:00"),
        _ev(3, "lesson_view", "2026-07-19T09:00:00+00:00"),   # Sunday, week end
    ])
    assert stats.weekly_streak_weeks(conn, today=TODAY) == 1


def test_weekly_streak_rollover_counts_adjacent_days_in_different_weeks_as_two(conn):
    monday = datetime.date(2026, 7, 20)
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-19T22:00:00+00:00"),   # Sunday, prior week
        _ev(2, "lesson_view", "2026-07-20T08:00:00+00:00"),   # Monday, this week
    ])
    assert stats.weekly_streak_weeks(conn, today=monday) == 2


def test_heatmap_forecast_excludes_dates_beyond_the_horizon(conn, tmp_path):
    content = _write_course(tmp_path)
    # three "good" reviews push the interval well past a 30-day forecast horizon
    events.insert_events(conn, [
        _ev(1, "lesson_reviewed", "2026-01-01T10:00:00+00:00",
            payload={"quality": "good"}),
        _ev(2, "lesson_reviewed", "2026-01-02T10:00:00+00:00",
            payload={"quality": "good"}),
        _ev(3, "lesson_reviewed", "2026-01-08T10:00:00+00:00",
            payload={"quality": "good"}),
    ])
    result = stats.heatmap(conn, content, today=TODAY)
    assert result["forecast"] == {}
