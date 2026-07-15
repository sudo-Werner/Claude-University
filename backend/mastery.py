import json

from backend import courses, srs

LEVELS = ["attempted", "familiar", "proficient", "mastered"]

# Summative evidence (exam questions) outweighs a formative check; the constant
# is the single tunable knob for that judgment call.
EXAM_WEIGHT = 2.0

_EXPLAIN_POINTS = {"correct": 1.0, "close": 0.5, "incorrect": 0.0}


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


def _accuracy_pool(conn, course_id):
    """Per-lesson weighted (points, total) evidence: lesson checks (incl. remediation
    practice, which logs as lesson_check), explain-it-back verdicts, and exam questions
    at EXAM_WEIGHT. prequiz_attempt is deliberately absent — it precedes instruction."""
    pool = {}

    def add(lesson_id, points, weight):
        if not lesson_id:
            return
        got, total = pool.get(lesson_id, (0.0, 0.0))
        pool[lesson_id] = (got + points, total + weight)

    rows = conn.execute(
        "SELECT topic_id, event_type, payload FROM events "
        "WHERE event_type IN ('lesson_check', 'lesson_explained', 'exam_result') "
        "AND course_id = ?",
        (course_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        if row["event_type"] == "lesson_check":
            add(row["topic_id"], 1.0 if payload.get("correct") else 0.0, 1.0)
        elif row["event_type"] == "lesson_explained":
            points = _EXPLAIN_POINTS.get(payload.get("verdict"))
            if points is not None:
                add(row["topic_id"], points, 1.0)
        else:  # exam_result: topic_id is the exam key — evidence lives per question
            for q in payload.get("perQuestion") or []:
                if not isinstance(q, dict):
                    continue
                try:
                    points = float(q.get("points"))
                except (TypeError, ValueError):
                    continue
                add(q.get("lessonId"), points * EXAM_WEIGHT, EXAM_WEIGHT)
    return pool


def lesson_mastery(conn, content_dir, course_id):
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return {}
    completed = courses.completed_lesson_ids(conn, course_id)
    reviews = srs.reviews_by_lesson(conn, course_id)
    pool = _accuracy_pool(conn, course_id)
    out = {}
    for lesson in courses.flatten_lessons(manifest):
        lid = lesson["id"]
        if lid not in completed:
            continue
        revs = reviews.get(lid)
        reps = srs.sm2(revs)["repetitions"] if revs else 0
        p = pool.get(lid)
        acc = (p[0] / p[1]) if p and p[1] else None
        out[lid] = level_for(reps, acc)
    return out


def mastery_counts(mastery_map):
    counts = {level: 0 for level in LEVELS}
    for level in mastery_map.values():
        counts[level] += 1
    return counts


def performance_summary(conn, content_dir, course_id):
    mastery_map = lesson_mastery(conn, content_dir, course_id)
    if not mastery_map:
        return ""
    counts = mastery_counts(mastery_map)
    pool = _accuracy_pool(conn, course_id)
    points = sum(p for p, _ in pool.values())
    total = sum(t for _, t in pool.values())
    acc = (points / total) if total else None
    n = len(mastery_map)
    proficient_plus = counts["proficient"] + counts["mastered"]
    if (acc is not None and acc < 0.6) or counts["attempted"] >= 2:
        return ("The learner has been struggling — reinforce fundamentals, go step-by-step, "
                "and add scaffolding with a brief recap of prerequisites.")
    if (acc is None or acc >= 0.8) and proficient_plus >= max(1, round(0.6 * n)):
        return ("The learner is performing strongly — you may go a bit deeper and faster, and "
                "assume earlier lessons are retained.")
    return "The learner is progressing steadily — keep a balanced pace."
