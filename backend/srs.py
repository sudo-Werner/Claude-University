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


def reviews_by_lesson(conn, course_id):
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
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            payload = {}
        quality = payload.get("quality", "good")
        try:
            date = datetime.date.fromisoformat(row["occurred_at"][:10])
        except ValueError:
            continue
        out.setdefault(row["topic_id"], []).append(
            {"quality": quality, "date": date, "at": row["occurred_at"]})
    return out


def _latest_exam_results(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    latest = {}
    for row in rows:
        if not row["topic_id"]:
            continue
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        try:
            date = datetime.date.fromisoformat(row["occurred_at"][:10])
        except ValueError:
            continue
        latest[row["topic_id"]] = {
            "at": row["occurred_at"],
            "date": date,
            "passed": bool(payload.get("passed")),
            "weak": {w.get("lessonId") for w in payload.get("weakSpots") or []
                     if isinstance(w, dict)},
        }
    return latest


def _weak_since_review(lesson_id, module_id, latest_results, last_review_at):
    """Bloom's corrective follow-up: a lesson flagged weak by the NEWEST result of an
    exam covering it stays due until it is reviewed or a newer attempt passes."""
    for key in (module_id, "final"):
        r = latest_results.get(key)
        if r and not r["passed"] and lesson_id in r["weak"]:
            if last_review_at is None or r["at"] > last_review_at:
                return True
    return False


def due_lesson_ids(conn, content_dir, course_id, today=None):
    today = today or datetime.date.today()
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return []
    by_lesson = reviews_by_lesson(conn, course_id)
    latest_results = _latest_exam_results(conn, course_id)
    due = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            lid = lesson.get("id")
            revs = by_lesson.get(lid)
            sched = sm2(revs) if revs else None
            if sched and sched["next_review"] is not None and sched["next_review"] <= today:
                due.append(lid)
                continue
            last_at = revs[-1]["at"] if revs else None
            if _weak_since_review(lid, module.get("id"), latest_results, last_at):
                due.append(lid)
    return due


def reviews_due_count(conn, content_dir, course_id, today=None):
    return len(due_lesson_ids(conn, content_dir, course_id, today))
