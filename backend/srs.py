import datetime
import json

from backend import courses

QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}


def sm2(reviews):
    ef = 2.5
    reps = 0
    interval = 0
    last = None
    for r in reviews:
        q = QUALITY.get(r["quality"], 4)
        last = r["date"]
        if q < 3:
            reps = 0
            interval = 0  # due again the same day
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = round(interval * ef)
            reps += 1
        ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        if ef < 1.3:
            ef = 1.3
    next_review = last + datetime.timedelta(days=interval) if last is not None else None
    return {
        "repetitions": reps,
        "interval_days": interval,
        "ease_factor": round(ef, 2),
        "last_reviewed": last,
        "next_review": next_review,
    }


def _reviews_by_lesson(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'lesson_reviewed' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    out = {}
    for row in rows:
        if not row["topic_id"]:
            continue
        payload = json.loads(row["payload"]) if row["payload"] else {}
        quality = payload.get("quality", "good")
        date = datetime.date.fromisoformat(row["occurred_at"][:10])
        out.setdefault(row["topic_id"], []).append({"quality": quality, "date": date})
    return out


def due_lesson_ids(conn, content_dir, course_id, today=None):
    today = today or datetime.date.today()
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return []
    by_lesson = _reviews_by_lesson(conn, course_id)
    due = []
    for lesson in courses.flatten_lessons(manifest):
        revs = by_lesson.get(lesson["id"])
        if not revs:
            continue
        sched = sm2(revs)
        if sched["next_review"] is not None and sched["next_review"] <= today:
            due.append(lesson["id"])
    return due


def reviews_due_count(conn, content_dir, course_id, today=None):
    return len(due_lesson_ids(conn, content_dir, course_id, today))
