import datetime
import json

from backend import courses

# A streak day is a day the learner actually studied — opened a lesson or
# completed a review. session_start (just opening the app) does not count.
STUDY_EVENTS = ("lesson_view", "lesson_reviewed")

# Event types worth showing in the study log. Checks, hints, and timer ticks
# are noise at log granularity and are filtered out here, server-side.
ACTIVITY_EVENTS = ("lesson_view", "lesson_reviewed", "course_created", "course_revised")


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


def _course_titles(content_dir, course_id, cache):
    if course_id not in cache:
        manifest = courses.load_manifest(content_dir, course_id)
        if manifest is None:
            cache[course_id] = (course_id, {})  # deleted/renamed course — show raw id
        else:
            cache[course_id] = (
                manifest.get("title") or course_id,
                {l["id"]: l["title"] for l in courses.flatten_lessons(manifest)},
            )
    return cache[course_id]


def recent_activity(conn, content_dir, limit=50):
    """Newest-first study log entries with titles resolved from course manifests."""
    placeholders = ",".join("?" * len(ACTIVITY_EVENTS))
    rows = conn.execute(
        f"SELECT course_id, topic_id, event_type, occurred_at, payload FROM events "
        f"WHERE event_type IN ({placeholders}) ORDER BY occurred_at DESC, id DESC LIMIT ?",
        (*ACTIVITY_EVENTS, limit),
    ).fetchall()
    cache = {}
    out = []
    for r in rows:
        course_title, lesson_titles = (None, {})
        if r["course_id"]:
            course_title, lesson_titles = _course_titles(content_dir, r["course_id"], cache)
        payload = json.loads(r["payload"]) if r["payload"] else {}
        out.append({
            "occurredAt": r["occurred_at"],
            "type": r["event_type"],
            "courseTitle": course_title,
            "lessonTitle": lesson_titles.get(r["topic_id"]) if r["topic_id"] else None,
            "quality": payload.get("quality"),
        })
    return out
