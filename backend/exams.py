"""Summative assessment: module exams + course final (sub-project C).

An exam is generated fresh per attempt from a BLUEPRINT — an ordered list of
slots, each naming the objective a question must test — so constructive
alignment is enforced by validation, not hoped for. The full exam (with the
answer key) lives server-side in content/courses/<id>/exams/<examKey>.json
until it is graded; the browser only ever sees the key-stripped client view.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import courses, events, fsutil, generation

MODULE_EXAM_QUESTIONS = 10
FINAL_EXAM_QUESTIONS = 18
PASS_SCORE = 0.8
MCQ_BLOOMS = ("remember", "understand")
HIGHER_BLOOMS = ("apply", "analyze", "evaluate", "create")
MAX_FREE_ANSWER_CHARS = 5000


# ---- blueprints ----

def _slot(lesson_id, objective):
    bloom = objective.get("bloom", "")
    return {
        "lessonId": lesson_id,
        "objectiveText": objective.get("text", ""),
        "bloom": bloom,
        "type": "mcq" if bloom in MCQ_BLOOMS else "free",
    }


def _fallback_objective(title):
    return {"text": f'Explain the key ideas of "{title}"', "bloom": "understand"}


def module_blueprint(manifest, module_id):
    module = next((m for m in manifest.get("modules", []) if m.get("id") == module_id), None)
    if module is None:
        return None
    per_lesson = []
    for lesson in module.get("lessons", []):
        objs = [o for o in lesson.get("objectives", []) or []
                if isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip()]
        if not objs:
            objs = [_fallback_objective(lesson.get("title", ""))]
        per_lesson.append((lesson.get("id", ""), objs))
    if not per_lesson:
        return None
    # Round-robin across lessons: every lesson is covered before any lesson gets a
    # second question; objectives cycle within a lesson if it runs out.
    # The exam grows past MODULE_EXAM_QUESTIONS only when a module has more lessons
    # than the base size — coverage of every lesson is the invariant.
    target = max(MODULE_EXAM_QUESTIONS, len(per_lesson))
    slots = []
    i = 0
    while len(slots) < target:
        lesson_id, objs = per_lesson[i % len(per_lesson)]
        rounds = i // len(per_lesson)
        slots.append(_slot(lesson_id, objs[rounds % len(objs)]))
        i += 1
    return slots


def final_blueprint(manifest):
    per_module = []
    for module in manifest.get("modules", []):
        higher, lower = [], []
        for lesson in module.get("lessons", []):
            for o in lesson.get("objectives", []) or []:
                if not (isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip()):
                    continue
                (higher if o.get("bloom") in HIGHER_BLOOMS else lower).append((lesson.get("id", ""), o))
        if not (higher or lower):
            lessons = module.get("lessons", [])
            if not lessons:
                continue
            lower.append((lessons[0].get("id", ""), _fallback_objective(module.get("title", ""))))
        # Higher-order objectives first so the round-robin below samples them first
        # (the "at least half apply-or-higher" goal is best-effort by construction).
        per_module.append(higher + lower)
    if not per_module:
        return None
    # The exam grows past FINAL_EXAM_QUESTIONS only when the course has more modules
    # than the base size — coverage of every module is the invariant.
    target = max(FINAL_EXAM_QUESTIONS, len(per_module))
    slots = []
    i = 0
    while len(slots) < target:
        pool = per_module[i % len(per_module)]
        rounds = i // len(per_module)
        lesson_id, obj = pool[rounds % len(pool)]
        slots.append(_slot(lesson_id, obj))
        i += 1
    return slots


def blueprint(manifest, exam_key):
    if exam_key == "final":
        return final_blueprint(manifest)
    return module_blueprint(manifest, exam_key)


# ---- generation prompt + validation ----

def _spine_vocab(slots, spine_lessons):
    lines = []
    seen = set()
    for s in slots:
        entry = (spine_lessons or {}).get(s["lessonId"]) or {}
        for c in entry.get("concepts", []) or []:
            term, definition = c.get("term", ""), c.get("definition", "")
            if term and definition and term not in seen:
                seen.add(term)
                lines.append(f"- {term} = {definition}")
    return lines[:40]


def exam_prompt(*, manifest, exam_key, slots, spine_lessons):
    if exam_key == "final":
        scope = "a comprehensive FINAL EXAM for the whole course"
        outcomes = [o.get("text", "") if isinstance(o, dict) else str(o)
                    for o in manifest.get("outcomes", []) or []]
    else:
        module = next((m for m in manifest.get("modules", []) if m.get("id") == exam_key), None)
        scope = f'a MODULE EXAM for the module "{(module or {}).get("title", "")}"'
        outcomes = [str(o) for o in (module or {}).get("outcomes", []) or []]
    slot_lines = []
    for i, s in enumerate(slots, start=1):
        slot_lines.append(
            f'{i}. type={s["type"]} lessonId={s["lessonId"]} bloom={s["bloom"]} '
            f'objective: {s["objectiveText"]}'
        )
    vocab = _spine_vocab(slots, spine_lessons)
    vocab_block = ("Use EXACTLY this course vocabulary:\n" + "\n".join(vocab) + "\n\n") if vocab else ""
    return (
        f'You are writing {scope} of the course "{manifest.get("title", "")}" on a personal '
        "learning platform. The exam must test the stated objectives — nothing else.\n"
        f"Course context: {manifest.get('brief', '')}\n"
        + (f"Outcomes to assess: {'; '.join(o for o in outcomes if o)}\n" if any(outcomes) else "")
        + vocab_block +
        "Write EXACTLY one question per slot below, in the SAME ORDER. Each question must "
        "genuinely test its slot's objective at its Bloom level.\n"
        + "\n".join(slot_lines) + "\n\n"
        "For type=mcq: a question with exactly 4 plausible choices (one correct, three "
        "believable distractors drawn from real misconceptions) and the 0-based answerIndex.\n"
        "For type=free: a short-answer question a learner answers in 2-6 sentences, plus "
        "modelAnswer (the reference answer) and graderNotes (what a correct answer must "
        "include, what earns partial credit). Free questions test apply-or-higher objectives: "
        "pose a NOVEL scenario, case, or problem that does not appear in the lessons — the "
        "learner must USE the concept to resolve it, not describe the concept. Write "
        "graderNotes to reward correct application to the scenario over recitation of "
        "definitions.\n"
        "Before emitting, re-answer each multiple-choice question independently from the "
        "question text alone. Confirm the choice at answerIndex is the answer you get, and "
        "that no distractor is also defensibly correct — if one is, rewrite it. For free "
        "questions, modelAnswer must be verifiably correct; state nothing you are not certain "
        "of.\n"
        "Question prompts and choices may use simple HTML (p, em, strong, code) and no other "
        "tags. Echo each slot's type and lessonId verbatim.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"questions":[{"type":"mcq","lessonId":"<from slot>","prompt":"<html>",'
        '"choices":["a","b","c","d"],"answerIndex":0}'
        ' | {"type":"free","lessonId":"<from slot>","prompt":"<html>",'
        '"modelAnswer":"<text>","graderNotes":"<text>"}]}'
    )


def _nonempty_str(v):
    return isinstance(v, str) and bool(v.strip())


def valid_exam(obj, slots):
    if not isinstance(obj, dict):
        return False
    questions = obj.get("questions")
    if not isinstance(questions, list) or len(questions) != len(slots):
        return False
    for q, s in zip(questions, slots):
        if not isinstance(q, dict):
            return False
        if q.get("type") != s["type"] or q.get("lessonId") != s["lessonId"]:
            return False
        if not _nonempty_str(q.get("prompt")):
            return False
        if s["type"] == "mcq":
            choices = q.get("choices")
            if not (isinstance(choices, list) and 3 <= len(choices) <= 5
                    and all(_nonempty_str(c) for c in choices)):
                return False
            idx = q.get("answerIndex")
            if not (isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(choices)):
                return False
        else:
            if not (_nonempty_str(q.get("modelAnswer")) and _nonempty_str(q.get("graderNotes"))):
                return False
    return True


def finalize_exam(obj, slots, exam_key, course_id):
    questions = []
    for q, s in zip(obj["questions"], slots):
        prompt = generation.sanitize_html(q["prompt"])

        out = {
            "type": s["type"],
            "lessonId": s["lessonId"],
            "objectiveText": s["objectiveText"],
            "bloom": s["bloom"],
            "prompt": prompt,
        }
        if s["type"] == "mcq":
            choices = [generation.sanitize_html(c) for c in q["choices"]]
            out["choices"] = choices
            out["answerIndex"] = q["answerIndex"]
        else:
            out["modelAnswer"] = q["modelAnswer"]
            out["graderNotes"] = q["graderNotes"]
        questions.append(out)
    return {
        "examKey": exam_key,
        "courseId": course_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }


_SERVER_ONLY_KEYS = ("answerIndex", "modelAnswer", "graderNotes")


def client_view(exam):
    questions = []
    for q in exam["questions"]:
        questions.append({k: v for k, v in q.items() if k not in _SERVER_ONLY_KEYS})
    return {"examKey": exam["examKey"], "questions": questions}


# ---- pending exam files ----

def _exam_path(content_dir, course_id, exam_key):
    return Path(content_dir) / course_id / "exams" / f"{exam_key}.json"


def save_pending(content_dir, course_id, exam):
    path = _exam_path(content_dir, course_id, exam["examKey"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(exam, indent=2, ensure_ascii=False))


def load_pending(content_dir, course_id, exam_key):
    path = _exam_path(content_dir, course_id, exam_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("questions"), list) else None


def delete_pending(content_dir, course_id, exam_key):
    _exam_path(content_dir, course_id, exam_key).unlink(missing_ok=True)


def prune_pending(content_dir, course_id, keep_keys):
    exams_dir = Path(content_dir) / course_id / "exams"
    if not exams_dir.is_dir():
        return
    for f in exams_dir.glob("*.json"):
        if f.stem not in keep_keys:
            f.unlink(missing_ok=True)


# ---- grading ----

_POINTS = {"correct": 1.0, "close": 0.5, "incorrect": 0.0}


def validate_answers(exam, answers):
    questions = exam["questions"]
    if not isinstance(answers, list) or len(answers) != len(questions):
        return "answers must match the exam's questions"
    for q, a in zip(questions, answers):
        if q["type"] == "mcq":
            if not (isinstance(a, int) and not isinstance(a, bool) and 0 <= a < len(q["choices"])):
                return "each multiple-choice answer must be a valid choice index"
        else:
            if not isinstance(a, str):
                return "each written answer must be text"
            if len(a) > MAX_FREE_ANSWER_CHARS:
                return f"written answers are limited to {MAX_FREE_ANSWER_CHARS} characters"
    return None


def exam_grade_prompt(exam, answers):
    items = []
    for i, (q, a) in enumerate(zip(exam["questions"], answers)):
        if q["type"] != "free":
            continue
        items.append(json.dumps({
            "index": i,
            "question": q["prompt"],
            "referenceAnswer": q["modelAnswer"],
            "gradingNotes": q["graderNotes"],
            "learnerAnswer": a,
        }, ensure_ascii=False))
    return (
        "You are a fair, rigorous examiner grading written exam answers on a personal "
        "learning platform. Judge understanding against the reference answer and grading "
        "notes — not wording. An empty answer is incorrect.\n\n"
        "Answers to grade, one JSON object per line:\n"
        + "\n".join(items) + "\n\n"
        "Grade each item independently. For each grade include evidence: a short verbatim "
        "quote from the learner's answer that your verdict rests on (empty string only if "
        "the answer is empty). Base the verdict only on what the evidence shows.\n"
        "Grade EVERY item. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"grades":[{"index":<same index>,"verdict":"correct"|"close"|"incorrect",'
        '"note":"<one or two sentences addressed to \'you\': what you got right and what '
        'was missing or wrong>","evidence":"<short quote from the learner\'s answer>"}]}'
    )


def valid_exam_grades(expected_indices):
    expected = set(expected_indices)

    def check(obj):
        grades = obj.get("grades") if isinstance(obj, dict) else None
        if not isinstance(grades, list):
            return False
        seen = set()
        for g in grades:
            if not isinstance(g, dict) or g.get("verdict") not in generation._GRADE_VERDICTS:
                return False
            if not _nonempty_str(g.get("note")):
                return False
            if not isinstance(g.get("evidence"), str):
                return False
            idx = g.get("index")
            if idx in seen:
                return False  # duplicate grade for one question — ambiguous, reject
            seen.add(idx)
        return seen == expected

    return check


def grade_exam(exam, answers, manifest, *, generate):
    questions = exam["questions"]
    free_indices = [i for i, q in enumerate(questions) if q["type"] == "free"]
    grades = {}
    if free_indices:
        result = generate(exam_grade_prompt(exam, answers), valid_exam_grades(free_indices))
        grades = {g["index"]: g for g in result["grades"]}
    per_question = []
    for i, (q, a) in enumerate(zip(questions, answers)):
        base = {
            "type": q["type"],
            "prompt": q["prompt"],
            "objectiveText": q["objectiveText"],
            "bloom": q["bloom"],
            "lessonId": q["lessonId"],
            "answer": a,
        }
        if q["type"] == "mcq":
            correct = a == q["answerIndex"]
            per_question.append({**base, "points": 1.0 if correct else 0.0,
                                 "correct": correct, "correctIndex": q["answerIndex"],
                                 "choices": q["choices"]})
        else:
            g = grades[i]
            # g["evidence"] is a reliability lever for the grader (quote-then-judge), not
            # learner-facing — intentionally not copied into per_question/the result payload.
            per_question.append({**base, "points": _POINTS[g["verdict"]],
                                 "verdict": g["verdict"],
                                 "note": generation.sanitize_html(g["note"])})
    points = sum(q["points"] for q in per_question)
    score = round(points / len(per_question), 4)
    return {
        "score": score,
        "passed": score >= PASS_SCORE,
        "perQuestion": per_question,
        "weakSpots": _weak_spots(per_question, manifest),
    }


def _weak_spots(per_question, manifest):
    titles = {l["id"]: l["title"] for l in courses.flatten_lessons(manifest)}
    by_lesson = {}
    for q in per_question:
        got, possible, missed = by_lesson.setdefault(q["lessonId"], [0.0, 0.0, []])
        by_lesson[q["lessonId"]][0] = got + q["points"]
        by_lesson[q["lessonId"]][1] = possible + 1.0
        if q["points"] < 1.0 and q["objectiveText"] not in missed:
            missed.append(q["objectiveText"])
    spots = []
    for lesson_id in titles:  # manifest order
        if lesson_id not in by_lesson:
            continue
        got, possible, missed = by_lesson[lesson_id]
        if possible and got / possible < PASS_SCORE:
            spots.append({"lessonId": lesson_id, "lessonTitle": titles[lesson_id],
                          "objectives": missed})
    return spots


# ---- results as events (server-recorded; learner state lives in the events DB) ----

def record_result(conn, course_id, exam_key, result):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ? AND topic_id = ?",
        (course_id, exam_key),
    ).fetchone()
    attempt = row["n"] + 1
    events.insert_events(conn, [{
        "client_event_id": f"server-{uuid.uuid4()}",
        "session_id": "server",
        "device": "server",
        "topic_id": exam_key,
        "course_id": course_id,
        "event_type": "exam_result",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {**result, "attempt": attempt},
    }])
    return attempt


def submit_exam(content_dir, conn, course_id, exam_key, answers, *, manifest, generate):
    """Grade the pending exam and consume it. Returns the result dict, or None when
    no exam is pending. Raises ValueError on malformed answers and lets ClaudeError
    propagate — in both cases the pending exam file survives, so the learner can
    resubmit without re-sitting."""
    exam = load_pending(content_dir, course_id, exam_key)
    if exam is None:
        return None
    error = validate_answers(exam, answers)
    if error:
        raise ValueError(error)
    result = grade_exam(exam, answers, manifest, generate=generate)
    result["attempt"] = record_result(conn, course_id, exam_key, result)
    delete_pending(content_dir, course_id, exam_key)
    return result


# ---- live status from events ----

def exam_status(conn, course_id, manifest):
    valid_keys = {m.get("id") for m in manifest.get("modules", [])} | {"final"}
    rows = conn.execute(
        "SELECT topic_id, payload FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ?",
        (course_id,),
    ).fetchall()
    status = {}
    for row in rows:
        key = row["topic_id"]
        if key not in valid_keys:
            continue  # exam for a module dropped by a later revision
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = status.setdefault(key, {"attempts": 0, "bestScore": 0.0, "passed": False})
        entry["attempts"] += 1
        score = payload.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            entry["bestScore"] = max(entry["bestScore"], float(score))
        entry["passed"] = entry["passed"] or bool(payload.get("passed"))
    return status


def course_passed(status, manifest):
    modules = manifest.get("modules", [])
    if not modules:
        return False
    keys = [m.get("id") for m in modules] + ["final"]
    return all(status.get(k, {}).get("passed") for k in keys)


def final_unlocked(status, manifest):
    """The comprehensive final is earned: it opens only once every module exam
    is passed (mastery-learning gate — the single hard gate in the platform)."""
    modules = manifest.get("modules", [])
    return bool(modules) and all(status.get(m.get("id"), {}).get("passed") for m in modules)
