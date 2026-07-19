import datetime
import json
from pathlib import Path

from backend import courses, srs

HEATMAP_PAST_DAYS = 370
HEATMAP_FORECAST_DAYS = 30

# A streak day is a day the learner actually studied — opened a lesson, completed a
# review, attempted a pre-quiz, sat an exam, worked a gap review, or played an
# Arcade round. session_start (just opening the app) does not count.
STUDY_EVENTS = ("lesson_view", "lesson_reviewed", "prequiz_attempt",
                "exam_result", "remediation_started", "capstone_result", "quiz_round")

# Event types worth showing in the study log, including Arcade rounds. Checks,
# hints, and timer ticks are noise at log granularity and are filtered out here,
# server-side.
ACTIVITY_EVENTS = ("lesson_view", "lesson_reviewed", "course_created", "course_revised",
                   "exam_result", "remediation_started", "capstone_result", "quiz_round")


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def _study_days(conn):
    """Distinct UTC calendar days with study activity, newest first."""
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
    return days


def streak_days(conn, today=None):
    """Consecutive UTC days with study activity, anchored at today or yesterday.

    The streak survives until a full day is missed: studying yesterday but not
    yet today keeps it alive. Returns 0 when the last study day is 2+ days ago.
    """
    today = today or _utc_today()
    days = _study_days(conn)
    if not days or days[0] < today - datetime.timedelta(days=1):
        return 0
    streak = 1
    for prev, cur in zip(days, days[1:]):
        if prev - cur != datetime.timedelta(days=1):
            break
        streak += 1
    return streak


def _week_start(d):
    return d - datetime.timedelta(days=d.weekday())  # Monday-anchored


def weekly_streak_weeks(conn, today=None):
    """Consecutive Mon-Sun weeks with >=1 study day, anchored at the current week
    or the immediately preceding one — the same one-unit tolerance as streak_days,
    one level up (a week with zero study days breaks it; the current week not yet
    having one doesn't, as long as last week did).
    """
    today = today or _utc_today()
    days = _study_days(conn)
    if not days:
        return 0
    weeks = sorted({_week_start(d) for d in days}, reverse=True)
    this_week = _week_start(today)
    last_week = this_week - datetime.timedelta(days=7)
    if weeks[0] < last_week:
        return 0
    streak = 1
    for prev, cur in zip(weeks, weeks[1:]):
        if prev - cur != datetime.timedelta(days=7):
            break
        streak += 1
    return streak


def heatmap(conn, content_dir, today=None):
    """Past study-day counts (all courses, from STUDY_EVENTS, last ~year) plus a
    forecast of upcoming SM-2-scheduled review load (all courses, next 30 days).

    Only the SM-2 schedule can be forecast — a lesson going due because an exam
    or quiz round revealed a weak spot is a reactive trigger with no future date,
    so it surfaces as due today (srs.due_lesson_ids) rather than in this forecast.
    """
    today = today or _utc_today()
    window_start = (today - datetime.timedelta(days=HEATMAP_PAST_DAYS)).isoformat()
    placeholders = ",".join("?" * len(STUDY_EVENTS))
    rows = conn.execute(
        f"SELECT substr(occurred_at, 1, 10) AS day, COUNT(*) AS n FROM events "
        f"WHERE event_type IN ({placeholders}) AND substr(occurred_at, 1, 10) >= ? "
        f"GROUP BY day",
        (*STUDY_EVENTS, window_start),
    ).fetchall()
    past = {}
    for r in rows:
        try:
            datetime.date.fromisoformat(r["day"])
        except ValueError:
            continue  # malformed timestamp — skip rather than crash the dashboard
        past[r["day"]] = r["n"]

    forecast = {}
    horizon = today + datetime.timedelta(days=HEATMAP_FORECAST_DAYS)
    content_dir = Path(content_dir)
    if content_dir.exists():
        for child in sorted(content_dir.iterdir()):
            if not (child / "course.json").exists():
                continue
            manifest = courses.load_manifest(content_dir, child.name)
            if manifest is None:
                continue
            by_lesson = srs.reviews_by_lesson(conn, child.name)
            if not by_lesson:
                continue
            for module in manifest.get("modules", []):
                for lesson in module.get("lessons", []):
                    revs = by_lesson.get(lesson.get("id"))
                    if not revs:
                        continue
                    next_review = srs.sm2(revs)["next_review"]
                    if next_review is not None and today <= next_review <= horizon:
                        key = next_review.isoformat()
                        forecast[key] = forecast.get(key, 0) + 1
    return {"past": past, "forecast": forecast}


def _course_titles(content_dir, course_id, cache):
    if course_id not in cache:
        manifest = courses.load_manifest(content_dir, course_id)
        if manifest is None:
            cache[course_id] = (None, {}, {})  # deleted course — its entries are skipped
        else:
            cache[course_id] = (
                manifest.get("title") or course_id,
                {l["id"]: l["title"] for l in courses.flatten_lessons(manifest)},
                {m.get("id"): m.get("title", "") for m in manifest.get("modules", [])},
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
        course_title, lesson_titles, module_titles = (None, {}, {})
        if r["course_id"]:
            course_title, lesson_titles, module_titles = _course_titles(
                content_dir, r["course_id"], cache)
            if course_title is None:
                continue  # course was deleted — stale history is noise in the log
        try:
            payload = json.loads(r["payload"]) if r["payload"] else {}
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        entry = {
            "occurredAt": r["occurred_at"],
            "type": r["event_type"],
            "courseTitle": course_title,
            "lessonTitle": lesson_titles.get(r["topic_id"]) if r["topic_id"] else None,
            "quality": payload.get("quality"),
        }
        if r["event_type"] in ("exam_result", "remediation_started", "capstone_result"):
            key = r["topic_id"]
            if r["event_type"] == "capstone_result":
                entry["examLabel"] = ("Course capstone" if key == "course"
                                      else f'{module_titles.get(key, "Module")} capstone')
            else:
                entry["examLabel"] = ("Final exam" if key == "final"
                                      else f'{module_titles.get(key, "Module")} exam')
            if r["event_type"] in ("exam_result", "capstone_result"):
                entry["score"] = payload.get("score")
                entry["passed"] = bool(payload.get("passed"))
        if r["event_type"] == "quiz_round":
            score, total = payload.get("score"), payload.get("total")
            if (isinstance(score, int) and not isinstance(score, bool)
                    and isinstance(total, int) and not isinstance(total, bool)
                    and total > 0):
                entry["score"] = score
                entry["total"] = total
        out.append(entry)
    return out
