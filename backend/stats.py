import datetime

# A streak day is a day the learner actually studied — opened a lesson or
# completed a review. session_start (just opening the app) does not count.
STUDY_EVENTS = ("lesson_view", "lesson_reviewed")


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def streak_days(conn, today=None):
    """Consecutive UTC days with study activity, anchored at today or yesterday.

    The streak survives until a full day is missed: studying yesterday but not
    yet today keeps it alive. Returns 0 when the last study day is 2+ days ago.
    """
    today = today or _utc_today()
    placeholders = ",".join("?" * len(STUDY_EVENTS))
    rows = conn.execute(
        f"SELECT DISTINCT substr(occurred_at, 1, 10) AS day FROM events "
        f"WHERE event_type IN ({placeholders}) ORDER BY day DESC",
        STUDY_EVENTS,
    ).fetchall()
    days = []
    for r in rows:
        try:
            days.append(datetime.date.fromisoformat(r["day"]))
        except ValueError:
            continue  # malformed timestamp — skip rather than crash the dashboard
    if not days or days[0] < today - datetime.timedelta(days=1):
        return 0
    streak = 1
    for prev, cur in zip(days, days[1:]):
        if prev - cur != datetime.timedelta(days=1):
            break
        streak += 1
    return streak
