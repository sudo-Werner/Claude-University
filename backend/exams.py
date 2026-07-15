"""Summative assessment: module exams + course final (sub-project C).

An exam is generated fresh per attempt from a BLUEPRINT — an ordered list of
slots, each naming the objective a question must test — so constructive
alignment is enforced by validation, not hoped for. The full exam (with the
answer key) lives server-side in content/courses/<id>/exams/<examKey>.json
until it is graded; the browser only ever sees the key-stripped client view.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from backend import courses, fsutil, generation

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
    slots = []
    i = 0
    while len(slots) < MODULE_EXAM_QUESTIONS:
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
    slots = []
    i = 0
    while len(slots) < FINAL_EXAM_QUESTIONS:
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
        "include, what earns partial credit).\n"
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


def _strip_html_attributes(html_str):
    """Remove all HTML attributes to prevent event handlers and dangerous markup.

    Converts <tag attr="value"> to <tag> before sanitizing.
    """
    return re.sub(r'<(\w+)[^>]*>', r'<\1>', html_str)


def finalize_exam(obj, slots, exam_key, course_id):
    questions = []
    for q, s in zip(obj["questions"], slots):
        prompt = _strip_html_attributes(q["prompt"])
        prompt = generation.sanitize_html(prompt)

        out = {
            "type": s["type"],
            "lessonId": s["lessonId"],
            "objectiveText": s["objectiveText"],
            "bloom": s["bloom"],
            "prompt": prompt,
        }
        if s["type"] == "mcq":
            choices = [_strip_html_attributes(c) for c in q["choices"]]
            choices = [generation.sanitize_html(c) for c in choices]
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
