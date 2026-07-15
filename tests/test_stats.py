import datetime

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
