import json

from backend import courses, srs

LEVELS = ["attempted", "familiar", "proficient", "mastered"]


def level_for(reps, acc):
    if reps >= 3:
        base = 3
    elif reps == 2:
        base = 2
    elif reps == 1:
        base = 1
    else:
        base = 0
    if acc is not None:
        if acc < 0.5:
            base = min(base, 0)
        elif acc < 0.8:
            base = min(base, 2)
    return LEVELS[base]


def _checks_by_lesson(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, payload FROM events "
        "WHERE event_type = 'lesson_check' AND course_id = ?",
        (course_id,),
    ).fetchall()
    out = {}
    for row in rows:
        if not row["topic_id"]:
            continue
        payload = json.loads(row["payload"]) if row["payload"] else {}
        correct, total = out.get(row["topic_id"], (0, 0))
        total += 1
        if payload.get("correct"):
            correct += 1
        out[row["topic_id"]] = (correct, total)
    return out


def lesson_mastery(conn, content_dir, course_id):
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return {}
    completed = courses.completed_lesson_ids(conn, course_id)
    reviews = srs._reviews_by_lesson(conn, course_id)
    checks = _checks_by_lesson(conn, course_id)
    out = {}
    for lesson in courses.flatten_lessons(manifest):
        lid = lesson["id"]
        if lid not in completed:
            continue
        revs = reviews.get(lid)
        reps = srs.sm2(revs)["repetitions"] if revs else 0
        c = checks.get(lid)
        acc = (c[0] / c[1]) if c and c[1] else None
        out[lid] = level_for(reps, acc)
    return out


def mastery_counts(mastery_map):
    counts = {level: 0 for level in LEVELS}
    for level in mastery_map.values():
        counts[level] = counts.get(level, 0) + 1
    return counts


def performance_summary(conn, content_dir, course_id):
    mastery_map = lesson_mastery(conn, content_dir, course_id)
    if not mastery_map:
        return ""
    counts = mastery_counts(mastery_map)
    checks = _checks_by_lesson(conn, course_id)
    correct = sum(c for c, _ in checks.values())
    total = sum(t for _, t in checks.values())
    acc = (correct / total) if total else None
    n = len(mastery_map)
    proficient_plus = counts["proficient"] + counts["mastered"]
    if (acc is not None and acc < 0.6) or counts["attempted"] >= 2:
        return ("The learner has been struggling — reinforce fundamentals, go step-by-step, "
                "and add scaffolding with a brief recap of prerequisites.")
    if (acc is None or acc >= 0.8) and proficient_plus >= max(1, round(0.6 * n)):
        return ("The learner is performing strongly — you may go a bit deeper and faster, and "
                "assume earlier lessons are retained.")
    return "The learner is progressing steadily — keep a balanced pace."
