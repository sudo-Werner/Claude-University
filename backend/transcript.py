"""Global transcript: a live academic record assembled from exam_result events and
course manifests. Nothing is stored; deleting a course removes its rows. It records
learning on a personal platform — it is not a credential (charter)."""

import json
from pathlib import Path

from backend import courses, exams, mastery


def _first_pass_dates(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    dates = {}
    for row in rows:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("passed") and row["topic_id"] not in dates:
            dates[row["topic_id"]] = row["occurred_at"][:10]
    return dates


def _capstone_rows(conn, course_id, manifest):
    """Transcript rows for graded capstones (Item E): one row per scope with at
    least one capstone_result event, in manifest-module order with the course
    scope last. Scopes dropped by a later revision are skipped, and payloads are
    server-written but still parsed defensively — a forged client event with this
    type must never 500 the transcript, so malformed rows are skipped entirely
    (mirrors exams.exam_status)."""
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'capstone_result' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    module_titles = {m.get("id"): m.get("title", "") for m in manifest.get("modules", [])}
    by_scope = {}
    for row in rows:
        scope = row["topic_id"]
        if scope != "course" and scope not in module_titles:
            continue
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = by_scope.setdefault(scope, {
            "scope": scope,
            "title": "Course capstone" if scope == "course" else module_titles[scope],
            "attempts": 0, "bestScore": 0.0, "passed": False, "passedOn": None,
        })
        entry["attempts"] += 1
        score = payload.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            entry["bestScore"] = max(entry["bestScore"], float(score))
        if payload.get("passed"):
            entry["passed"] = True
            if entry["passedOn"] is None:
                entry["passedOn"] = row["occurred_at"][:10]
    order = [m.get("id") for m in manifest.get("modules", [])] + ["course"]
    return [by_scope[s] for s in order if s in by_scope]


def course_record(conn, content_dir, course_id, manifest):
    status = exams.exam_status(conn, course_id, manifest)
    dates = _first_pass_dates(conn, course_id)

    def row(key, title):
        s = status.get(key, {})
        return {"key": key, "title": title, "attempts": s.get("attempts", 0),
                "bestScore": s.get("bestScore", 0.0), "passed": bool(s.get("passed")),
                "passedOn": dates.get(key)}

    modules = [row(m.get("id"), m.get("title", "")) for m in manifest.get("modules", [])]
    passed = exams.course_passed(status, manifest)
    passed_on = None
    if passed:
        keys = [m.get("id") for m in manifest.get("modules", [])] + ["final"]
        passed_on = max(dates[k] for k in keys)  # the day the last requirement fell
    m = mastery.lesson_mastery(conn, content_dir, course_id)
    level = manifest.get("level") or {}
    return {
        "courseId": course_id,
        "title": manifest.get("title", ""),
        "modules": modules,
        "final": row("final", "Final exam"),
        "capstones": _capstone_rows(conn, course_id, manifest),
        "coursePassed": passed,
        "passedOn": passed_on,
        "masteryCounts": mastery.mastery_counts(m),
        "lessonsTotal": len(courses.flatten_lessons(manifest)),
        "lessonsCompleted": len(m),
        "level": level.get("label") or level.get("code"),
        "targetHours": manifest.get("targetHours"),
    }


def transcript(conn, content_dir):
    content_dir = Path(content_dir)
    out = []
    if not content_dir.exists():
        return out
    for child in sorted(content_dir.iterdir()):
        if not (child / "course.json").exists():
            continue
        manifest = courses.load_manifest(content_dir, child.name)
        if manifest is None:
            continue  # corrupt manifest: absent from the record, never a 500
        try:
            out.append(course_record(conn, content_dir, child.name, manifest))
        except (KeyError, TypeError):
            continue
    return out
