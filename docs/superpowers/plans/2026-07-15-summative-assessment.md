# Aligned Summative Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Module exams and a comprehensive course final, generated from Bloom objectives, graded server-side, pass at 80%, with a weak-spot report and unlimited fresh retakes.

**Architecture:** New `backend/exams.py` owns blueprints (which objective each question tests), the generation prompt + blueprint-aligned validator, pending-exam file I/O, grading math, and status computed live from `exam_result` events. Two new routes in `app.py` (start, submit). Frontend: new exam screen + result view, exam rows in the curriculum view.

**Tech Stack:** Flask + SQLite (events), Claude CLI via `backend/claude_client.run_structured`, vanilla-JS frontend with `node --test`.

## Global Constraints

- Module exam = exactly 10 questions, every lesson in the module contributes at least one; final = exactly 18 questions, at least one per module. `MODULE_EXAM_QUESTIONS = 10`, `FINAL_EXAM_QUESTIONS = 18`.
- Question format by Bloom level: `remember`/`understand` → `mcq`; `apply`/`analyze`/`evaluate`/`create` → `free`.
- Pass = score >= 0.8 (`PASS_SCORE = 0.8`); exactly 80% passes. Points: MCQ 1/0; free `correct`=1, `close`=0.5, `incorrect`=0.
- `answerIndex`, `modelAnswer`, `graderNotes` NEVER reach the browser. Question `prompt`/`choices` and free-response feedback `note` are server-sanitized via `generation.sanitize_html` and render RAW client-side (no client `esc()` — it would double-escape). Objective texts, lesson titles, and error strings are plain text and MUST be `esc()`'d client-side.
- Pending exam file: `content/courses/<course_id>/exams/<examKey>.json`, written with `fsutil.write_text_atomic`, deleted only after successful grading. `examKey` = a module id or the literal `final`.
- The server itself records the `exam_result` event (synthesized `client_event_id`/`session_id`); the client never posts it.
- Submit validation: 404 if no pending exam; 400 if answer count mismatches, an mcq answer is not an int in range, a free answer is not a string, or a free answer exceeds 5,000 characters.
- Backend tests: `.venv/bin/pytest`. Frontend tests: `node --test frontend/tests/*.test.js` (NEVER the bare directory — it silently runs nothing). After touching `frontend/src/app.js`: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`.
- No emojis anywhere. Commit after each task; never merge or push.

## File Structure

- `backend/exams.py` (new) — blueprints, prompt, validators, pending-file I/O, grading, status. Imports stdlib + `backend.fsutil`, `backend.courses`, `backend.spine`, `backend.generation`, `backend.events` only.
- `backend/app.py` — two new routes; `exams`/`coursePassed` added to `GET /api/courses/<id>`.
- `backend/courses.py` — `list_courses` summaries gain `passed`; `apply_revision` prunes pending exam files for dropped modules (deferred `from backend import exams` — `exams` imports `courses`, so a top-level import would be a cycle).
- `frontend/src/views/exam.js` (new) — `examHTML`, `examResultHTML`, `examReady`.
- `frontend/src/views/curriculum.js` — exam rows per module + final row + course-passed badge.
- `frontend/src/views/home.js` — passed badge on course cards.
- `frontend/src/views/loading.js` — `EXAM_STAGES`.
- `frontend/src/courses.js` — `startExam`, `submitExam`.
- `frontend/src/app.js` — `showExam` / `paintExam` / `submitCurrentExam` wiring.
- `frontend/styles.css` — exam styles.
- Tests: `tests/test_exams.py` (new), `tests/test_courses_api.py`, `tests/test_courses.py`, `frontend/tests/exam.test.js` (new), `frontend/tests/views.test.js`, `frontend/tests/courses.test.js`.

---

### Task 1: backend/exams.py — blueprints, prompt, validator, pending files

**Files:**
- Create: `backend/exams.py`
- Test: `tests/test_exams.py`

**Interfaces:**
- Produces: `module_blueprint(manifest, module_id) -> list[slot] | None`; `final_blueprint(manifest) -> list[slot] | None`; `blueprint(manifest, exam_key)` dispatching on `exam_key == "final"`; slot = `{"lessonId", "objectiveText", "bloom", "type"}`; `exam_prompt(*, manifest, exam_key, slots, spine_lessons) -> str`; `valid_exam(obj, slots) -> bool`; `finalize_exam(obj, slots, exam_key, course_id) -> dict`; `client_view(exam) -> dict`; `save_pending` / `load_pending` / `delete_pending` / `prune_pending`; constants `MODULE_EXAM_QUESTIONS`, `FINAL_EXAM_QUESTIONS`, `PASS_SCORE`, `MCQ_BLOOMS`, `HIGHER_BLOOMS`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exams.py`:

```python
import json

from backend import exams


def _manifest():
    def obj(text, bloom):
        return {"text": text, "bloom": bloom, "knowledge": "conceptual"}
    return {
        "id": "c1", "title": "Course One", "brief": "A course.",
        "outcomes": [{"text": "Do things", "bloom": "apply"}],
        "modules": [
            {"id": "m1", "title": "Module One",
             "outcomes": ["Understand basics"],
             "lessons": [
                 {"id": "c1-l1", "title": "L1", "objectives": [obj("o1a", "remember"), obj("o1b", "apply")]},
                 {"id": "c1-l2", "title": "L2", "objectives": [obj("o2a", "understand")]},
                 {"id": "c1-l3", "title": "L3", "objectives": [obj("o3a", "analyze"), obj("o3b", "evaluate")]},
             ]},
            {"id": "m2", "title": "Module Two",
             "lessons": [
                 {"id": "c1-l4", "title": "L4", "objectives": [obj("o4a", "apply"), obj("o4b", "remember")]},
                 {"id": "c1-l5", "title": "L5", "objectives": [obj("o5a", "create")]},
             ]},
        ],
    }


def _questions_for(slots):
    out = []
    for s in slots:
        q = {"type": s["type"], "lessonId": s["lessonId"], "prompt": "<p>Q?</p>"}
        if s["type"] == "mcq":
            q["choices"] = ["a", "b", "c", "d"]
            q["answerIndex"] = 1
        else:
            q["modelAnswer"] = "ref"
            q["graderNotes"] = "notes"
        out.append(q)
    return {"questions": out}


def test_module_blueprint_covers_every_lesson_exactly_ten():
    slots = exams.module_blueprint(_manifest(), "m1")
    assert len(slots) == exams.MODULE_EXAM_QUESTIONS == 10
    assert {s["lessonId"] for s in slots} == {"c1-l1", "c1-l2", "c1-l3"}


def test_module_blueprint_formats_follow_bloom():
    slots = exams.module_blueprint(_manifest(), "m1")
    for s in slots:
        expected = "mcq" if s["bloom"] in exams.MCQ_BLOOMS else "free"
        assert s["type"] == expected


def test_module_blueprint_unknown_module_is_none():
    assert exams.module_blueprint(_manifest(), "nope") is None


def test_final_blueprint_covers_every_module_exactly_eighteen():
    slots = exams.final_blueprint(_manifest())
    assert len(slots) == exams.FINAL_EXAM_QUESTIONS == 18
    lesson_module = {"c1-l1": "m1", "c1-l2": "m1", "c1-l3": "m1", "c1-l4": "m2", "c1-l5": "m2"}
    assert {lesson_module[s["lessonId"]] for s in slots} == {"m1", "m2"}


def test_final_blueprint_prefers_higher_order():
    slots = exams.final_blueprint(_manifest())
    higher = sum(1 for s in slots if s["bloom"] in exams.HIGHER_BLOOMS)
    assert higher >= len(slots) // 2


def test_blueprint_dispatch():
    m = _manifest()
    assert exams.blueprint(m, "final") == exams.final_blueprint(m)
    assert exams.blueprint(m, "m1") == exams.module_blueprint(m, "m1")


def test_lesson_without_objectives_gets_fallback_slot():
    m = _manifest()
    m["modules"][0]["lessons"][1]["objectives"] = []
    slots = exams.module_blueprint(m, "m1")
    assert any(s["lessonId"] == "c1-l2" for s in slots)


def test_exam_prompt_mentions_slots_and_spine():
    m = _manifest()
    slots = exams.module_blueprint(m, "m1")
    spine_lessons = {"c1-l1": {"summary": "s", "concepts": [{"term": "gradient", "definition": "slope of loss"}]}}
    p = exams.exam_prompt(manifest=m, exam_key="m1", slots=slots, spine_lessons=spine_lessons)
    assert "o1a" in p and "c1-l1" in p and "gradient = slope of loss" in p
    assert "answerIndex" in p and "modelAnswer" in p


def test_valid_exam_accepts_aligned_and_rejects_misaligned():
    slots = exams.module_blueprint(_manifest(), "m1")
    good = _questions_for(slots)
    assert exams.valid_exam(good, slots)
    short = {"questions": good["questions"][:-1]}
    assert not exams.valid_exam(short, slots)
    swapped = json.loads(json.dumps(good))
    swapped["questions"][0]["type"] = "free" if slots[0]["type"] == "mcq" else "mcq"
    assert not exams.valid_exam(swapped, slots)
    wrong_lesson = json.loads(json.dumps(good))
    wrong_lesson["questions"][0]["lessonId"] = "c1-l99"
    assert not exams.valid_exam(wrong_lesson, slots)


def test_valid_exam_rejects_bad_mcq_and_free_shapes():
    slots = exams.module_blueprint(_manifest(), "m1")
    mcq_i = next(i for i, s in enumerate(slots) if s["type"] == "mcq")
    free_i = next(i for i, s in enumerate(slots) if s["type"] == "free")
    base = _questions_for(slots)
    for mutate in (
        lambda q: q[mcq_i].update(choices=["a", "b"]),
        lambda q: q[mcq_i].update(answerIndex=9),
        lambda q: q[free_i].update(modelAnswer=""),
        lambda q: q[free_i].update(graderNotes=None),
        lambda q: q[free_i].update(prompt=" "),
    ):
        bad = json.loads(json.dumps(base))
        mutate(bad["questions"])
        assert not exams.valid_exam(bad, slots)


def test_finalize_sanitizes_and_stamps_slot_metadata():
    slots = exams.module_blueprint(_manifest(), "m1")
    raw = _questions_for(slots)
    raw["questions"][0]["prompt"] = '<p onclick="x">Q<script>bad()</script></p>'
    exam = exams.finalize_exam(raw, slots, "m1", "c1")
    assert exam["examKey"] == "m1" and exam["courseId"] == "c1"
    q0 = exam["questions"][0]
    assert "<script>" not in q0["prompt"] and "onclick" not in q0["prompt"]
    assert q0["objectiveText"] == slots[0]["objectiveText"]
    assert q0["bloom"] == slots[0]["bloom"]


def test_client_view_strips_all_keys():
    slots = exams.module_blueprint(_manifest(), "m1")
    exam = exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")
    view = exams.client_view(exam)
    blob = json.dumps(view)
    assert "answerIndex" not in blob and "modelAnswer" not in blob and "graderNotes" not in blob
    assert len(view["questions"]) == 10 and view["examKey"] == "m1"


def test_pending_roundtrip_and_prune(tmp_path):
    slots = exams.module_blueprint(_manifest(), "m1")
    exam = exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")
    exams.save_pending(tmp_path, "c1", exam)
    assert exams.load_pending(tmp_path, "c1", "m1")["examKey"] == "m1"
    assert exams.load_pending(tmp_path, "c1", "final") is None
    (tmp_path / "c1" / "exams" / "m9.json").write_text("{}")
    (tmp_path / "c1" / "exams" / "final.json").write_text(json.dumps(exam))
    exams.prune_pending(tmp_path, "c1", {"m1", "final"})
    assert not (tmp_path / "c1" / "exams" / "m9.json").exists()
    assert (tmp_path / "c1" / "exams" / "m1.json").exists()
    assert (tmp_path / "c1" / "exams" / "final.json").exists()
    exams.delete_pending(tmp_path, "c1", "m1")
    assert exams.load_pending(tmp_path, "c1", "m1") is None
    exams.delete_pending(tmp_path, "c1", "m1")  # idempotent


def test_load_pending_corrupt_is_none(tmp_path):
    p = tmp_path / "c1" / "exams"
    p.mkdir(parents=True)
    (p / "m1.json").write_text("{not json")
    assert exams.load_pending(tmp_path, "c1", "m1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_exams.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.exams'` (or ImportError).

- [ ] **Step 3: Implement backend/exams.py (part 1)**

Create `backend/exams.py`:

```python
"""Summative assessment: module exams + course final (sub-project C).

An exam is generated fresh per attempt from a BLUEPRINT — an ordered list of
slots, each naming the objective a question must test — so constructive
alignment is enforced by validation, not hoped for. The full exam (with the
answer key) lives server-side in content/courses/<id>/exams/<examKey>.json
until it is graded; the browser only ever sees the key-stripped client view.
"""

import json
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


def finalize_exam(obj, slots, exam_key, course_id):
    questions = []
    for q, s in zip(obj["questions"], slots):
        out = {
            "type": s["type"],
            "lessonId": s["lessonId"],
            "objectiveText": s["objectiveText"],
            "bloom": s["bloom"],
            "prompt": generation.sanitize_html(q["prompt"]),
        }
        if s["type"] == "mcq":
            out["choices"] = [generation.sanitize_html(c) for c in q["choices"]]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_exams.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest -q`
Expected: all PASS (288 existing + new).

- [ ] **Step 6: Commit**

```bash
git add backend/exams.py tests/test_exams.py
git commit -m "feat(exams): blueprints, prompt, validator, pending-exam files"
```

---

### Task 2: backend/exams.py — grading, result assembly, events, status

**Files:**
- Modify: `backend/exams.py` (append)
- Test: `tests/test_exams.py` (append)

**Interfaces:**
- Consumes: Task 1's `load_pending`/`delete_pending`, `PASS_SCORE`, `MAX_FREE_ANSWER_CHARS`; `generation._GRADE_VERDICTS`, `generation.sanitize_html`; `courses.flatten_lessons`; `events.insert_events`.
- Produces: `validate_answers(exam, answers) -> str | None` (error message or None); `exam_grade_prompt(exam, answers) -> str`; `valid_exam_grades(expected_indices) -> callable`; `grade_exam(exam, answers, manifest, *, generate) -> dict` where `generate(prompt, validate)`; `record_result(conn, course_id, exam_key, result) -> int` (attempt number); `submit_exam(content_dir, conn, course_id, exam_key, answers, *, manifest, generate) -> dict | None`; `exam_status(conn, course_id, manifest) -> dict`; `course_passed(status, manifest) -> bool`. Result dict: `{"score", "passed", "attempt", "perQuestion", "weakSpots"}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_exams.py`:

```python
def _exam(slots=None):
    slots = slots or exams.module_blueprint(_manifest(), "m1")
    return exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")


def _answers(exam, *, mcq=1, free="my answer"):
    return [mcq if q["type"] == "mcq" else free for q in exam["questions"]]


def _grader(verdict="correct", note="Good."):
    def generate(prompt, validate):
        import re
        idxs = [int(m) for m in re.findall(r'"index": (\d+)', prompt)]
        result = {"grades": [{"index": i, "verdict": verdict, "note": note} for i in idxs]}
        assert validate(result)
        return result
    return generate


def test_validate_answers_shapes():
    exam = _exam()
    assert exams.validate_answers(exam, _answers(exam)) is None
    assert exams.validate_answers(exam, "nope") is not None
    assert exams.validate_answers(exam, _answers(exam)[:-1]) is not None
    bad_mcq = _answers(exam)
    bad_mcq[[i for i, q in enumerate(exam["questions"]) if q["type"] == "mcq"][0]] = 99
    assert exams.validate_answers(exam, bad_mcq) is not None
    long_free = _answers(exam, free="x" * (exams.MAX_FREE_ANSWER_CHARS + 1))
    assert exams.validate_answers(exam, long_free) is not None
    empty_free_ok = _answers(exam, free="")
    assert exams.validate_answers(exam, empty_free_ok) is None


def test_exam_grade_prompt_lists_only_free_questions():
    exam = _exam()
    p = exams.exam_grade_prompt(exam, _answers(exam))
    free_count = sum(1 for q in exam["questions"] if q["type"] == "free")
    assert p.count('"learnerAnswer"') == free_count
    assert "my answer" in p and "graderNotes" not in p  # notes embedded under a different key


def test_valid_exam_grades_requires_exact_indices():
    check = exams.valid_exam_grades([1, 3])
    ok = {"grades": [{"index": 1, "verdict": "close", "note": "n"}, {"index": 3, "verdict": "correct", "note": "n"}]}
    assert check(ok)
    assert not check({"grades": ok["grades"][:1]})
    assert not check({"grades": ok["grades"] + [{"index": 9, "verdict": "correct", "note": "n"}]})
    assert not check({"grades": [{"index": 1, "verdict": "meh", "note": "n"}, {"index": 3, "verdict": "correct", "note": "n"}]})
    assert not check({"grades": [{"index": 1, "verdict": "close", "note": " "}, {"index": 3, "verdict": "correct", "note": "n"}]})


def test_grade_exam_all_correct_passes():
    exam = _exam()
    result = exams.grade_exam(exam, _answers(exam), _manifest(), generate=_grader())
    assert result["score"] == 1.0 and result["passed"] is True
    assert len(result["perQuestion"]) == 10 and result["weakSpots"] == []


def test_grade_exam_exactly_eighty_percent_passes():
    exam = _exam()
    mcq_idx = [i for i, q in enumerate(exam["questions"]) if q["type"] == "mcq"]
    free_count = 10 - len(mcq_idx)
    # Make wrong MCQs + close frees add up to exactly 2.0 lost points when possible;
    # fall back to asserting the boundary rule directly.
    assert exams.PASS_SCORE == 0.8
    answers = _answers(exam)
    wrong = 0
    for i in mcq_idx:
        if wrong == 2:
            break
        answers[i] = (exam["questions"][i]["answerIndex"] + 1) % len(exam["questions"][i]["choices"])
        wrong += 1
    if wrong == 2:
        result = exams.grade_exam(exam, answers, _manifest(), generate=_grader())
        assert result["score"] == 0.8 and result["passed"] is True


def test_grade_exam_failure_builds_weak_spots():
    exam = _exam()
    answers = _answers(exam)
    for i, q in enumerate(exam["questions"]):
        if q["type"] == "mcq":
            answers[i] = (q["answerIndex"] + 1) % len(q["choices"])
    result = exams.grade_exam(exam, answers, _manifest(), generate=_grader(verdict="incorrect", note="No."))
    assert result["score"] == 0.0 and result["passed"] is False
    assert {w["lessonId"] for w in result["weakSpots"]} == {"c1-l1", "c1-l2", "c1-l3"}
    spot = next(w for w in result["weakSpots"] if w["lessonId"] == "c1-l1")
    assert spot["lessonTitle"] == "L1" and spot["objectives"]


def test_grade_exam_sanitizes_grader_notes_and_reveals_mcq_key():
    exam = _exam()
    result = exams.grade_exam(exam, _answers(exam), _manifest(),
                              generate=_grader(note='<em>ok</em><script>x()</script>'))
    free_q = next(q for q in result["perQuestion"] if q["type"] == "free")
    assert "<script>" not in free_q["note"] and "<em>ok</em>" in free_q["note"]
    mcq_q = next(q for q in result["perQuestion"] if q["type"] == "mcq")
    assert isinstance(mcq_q["correctIndex"], int) and "answerIndex" not in mcq_q


def test_record_result_and_status(conn):
    manifest = _manifest()
    r1 = {"score": 0.6, "passed": False, "perQuestion": [], "weakSpots": []}
    r2 = {"score": 0.9, "passed": True, "perQuestion": [], "weakSpots": []}
    assert exams.record_result(conn, "c1", "m1", r1) == 1
    assert exams.record_result(conn, "c1", "m1", r2) == 2
    assert exams.record_result(conn, "c1", "final", r2) == 1
    status = exams.exam_status(conn, "c1", manifest)
    assert status["m1"] == {"attempts": 2, "bestScore": 0.9, "passed": True}
    assert status["final"]["passed"] is True and "m2" not in status
    assert exams.course_passed(status, manifest) is False  # m2 never taken
    exams.record_result(conn, "c1", "m2", r2)
    status = exams.exam_status(conn, "c1", manifest)
    assert exams.course_passed(status, manifest) is True


def test_status_ignores_dropped_module_keys(conn):
    manifest = _manifest()
    exams.record_result(conn, "c1", "m99", {"score": 1.0, "passed": True, "perQuestion": [], "weakSpots": []})
    status = exams.exam_status(conn, "c1", manifest)
    assert "m99" not in status


def test_submit_exam_full_cycle(tmp_path, conn):
    manifest = _manifest()
    exam = _exam()
    exams.save_pending(tmp_path, "c1", exam)
    result = exams.submit_exam(tmp_path, conn, "c1", "m1", _answers(exam),
                               manifest=manifest, generate=_grader())
    assert result["passed"] is True and result["attempt"] == 1
    assert exams.load_pending(tmp_path, "c1", "m1") is None  # consumed
    rows = conn.execute("SELECT event_type, topic_id, course_id FROM events").fetchall()
    assert ("exam_result", "m1", "c1") in [(r["event_type"], r["topic_id"], r["course_id"]) for r in rows]


def test_submit_exam_no_pending_is_none(tmp_path, conn):
    assert exams.submit_exam(tmp_path, conn, "c1", "m1", [], manifest=_manifest(), generate=_grader()) is None


def test_submit_exam_grading_failure_keeps_pending(tmp_path, conn):
    from backend import claude_client
    exam = _exam()
    exams.save_pending(tmp_path, "c1", exam)

    def boom(prompt, validate):
        raise claude_client.ClaudeError("nope")

    try:
        exams.submit_exam(tmp_path, conn, "c1", "m1", _answers(exam), manifest=_manifest(), generate=boom)
        assert False, "expected ClaudeError"
    except claude_client.ClaudeError:
        pass
    assert exams.load_pending(tmp_path, "c1", "m1") is not None  # NOT consumed
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_exams.py -q`
Expected: new tests FAIL with `AttributeError: module 'backend.exams' has no attribute ...`.

- [ ] **Step 3: Implement grading + status (append to backend/exams.py)**

Add `import uuid` to the imports and `from backend import events` (keep the import block alphabetical: `from backend import courses, events, fsutil, generation`). Then append:

```python
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
        "Grade EVERY item. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"grades":[{"index":<same index>,"verdict":"correct"|"close"|"incorrect",'
        '"note":"<one or two sentences addressed to \'you\': what you got right and what '
        'was missing or wrong>"}]}'
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
            seen.add(g.get("index"))
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
        entry = status.setdefault(key, {"attempts": 0, "bestScore": 0.0, "passed": False})
        entry["attempts"] += 1
        entry["bestScore"] = max(entry["bestScore"], float(payload.get("score") or 0.0))
        entry["passed"] = entry["passed"] or bool(payload.get("passed"))
    return status


def course_passed(status, manifest):
    modules = manifest.get("modules", [])
    if not modules:
        return False
    keys = [m.get("id") for m in modules] + ["final"]
    return all(status.get(k, {}).get("passed") for k in keys)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_exams.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite, then commit**

Run: `.venv/bin/pytest -q` — all PASS.

```bash
git add backend/exams.py tests/test_exams.py
git commit -m "feat(exams): grading, weak spots, server-recorded results, live status"
```

---

### Task 3: routes + course payloads + revision pruning

**Files:**
- Modify: `backend/app.py` (add two routes after the explain route; extend `get_course`)
- Modify: `backend/courses.py` (`list_courses` summaries; `apply_revision` tail)
- Test: `tests/test_courses_api.py`, `tests/test_courses.py`

**Interfaces:**
- Consumes: `exams.blueprint`, `exams.exam_prompt`, `exams.valid_exam`, `exams.finalize_exam`, `exams.client_view`, `exams.save_pending`, `exams.submit_exam`, `exams.exam_status`, `exams.course_passed`, `exams.prune_pending`; `generation._gen_lock`; `spine.load_spine`; `claude_client.run_structured`.
- Produces: `POST /api/courses/<course_id>/exams/<exam_key>` → 200 client view | 404 | 502/503; `POST /api/courses/<course_id>/exams/<exam_key>/submit` → 200 result | 400 | 404 | 502/503. `GET /api/courses/<id>` gains `"exams"` and `"coursePassed"`. `list_courses` summaries gain `"passed"`.

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_courses_api.py` (reuse its existing `_fixture_course` helper and imports; add `from backend import exams` at the top with the other backend imports):

```python
def _exam_generate_ok(slots):
    def fake(prompt, *, validate=None, **kw):
        qs = []
        for s in slots:
            q = {"type": s["type"], "lessonId": s["lessonId"], "prompt": "<p>Q?</p>"}
            if s["type"] == "mcq":
                q.update(choices=["a", "b", "c", "d"], answerIndex=0)
            else:
                q.update(modelAnswer="ref", graderNotes="notes")
            qs.append(q)
        obj = {"questions": qs}
        assert validate is None or validate(obj)
        return obj
    return fake


def test_start_exam_returns_stripped_questions(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    resp = client.post(f"/api/courses/{cid}/exams/m1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["examKey"] == "m1" and len(body["questions"]) == 10
    blob = resp.get_data(as_text=True)
    assert "answerIndex" not in blob and "modelAnswer" not in blob and "graderNotes" not in blob
    assert (root / cid / "exams" / "m1.json").exists()


def test_start_exam_unknown_key_404(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    assert client.post(f"/api/courses/{cid}/exams/m99").status_code == 404
    assert client.post("/api/courses/nope/exams/m1").status_code == 404


def test_start_exam_maps_claude_errors(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502


def test_submit_exam_roundtrip(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 200

    def fake_grade(prompt, *, validate=None, **kw):
        import re
        idxs = [int(m) for m in re.findall(r'"index": (\d+)', prompt)]
        return {"grades": [{"index": i, "verdict": "correct", "note": "Good."} for i in idxs]}

    monkeypatch.setattr(claude_client, "run_structured", fake_grade)
    exam = exams.load_pending(root, cid, "m1")
    answers = [0 if q["type"] == "mcq" else "ans" for q in exam["questions"]]
    resp = client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": answers})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True and body["attempt"] == 1
    # consumed: a second submit finds nothing pending
    assert client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": answers}).status_code == 404


def test_submit_exam_bad_answers_400(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.load_manifest(root, cid)
    slots = exams.blueprint(manifest, "m1")
    monkeypatch.setattr(claude_client, "run_structured", _exam_generate_ok(slots))
    client.post(f"/api/courses/{cid}/exams/m1")
    resp = client.post(f"/api/courses/{cid}/exams/m1/submit", json={"answers": ["wrong shape"]})
    assert resp.status_code == 400
    assert (root / cid / "exams" / "m1.json").exists()  # still pending


def test_get_course_includes_exam_status(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    resp = client.get(f"/api/courses/{cid}")
    body = resp.get_json()
    assert body["exams"] == {} and body["coursePassed"] is False
```

Note for the implementer: `_fixture_course` writes a small course; if its lessons lack `objectives`, the blueprint's fallback objective covers them — the tests above only rely on counts and types. If `_fixture_course` has fewer lessons than 10, the round-robin still yields exactly 10 slots.

Append to `tests/test_courses.py` (this file already defines `_valid_compiled(cid)` — a schemaVersion-2 course with one module `m1` — and `_make_course(tmp_path)`):

```python
def test_apply_revision_prunes_dropped_module_exams(tmp_path):
    from backend import courses
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [
            {"id": "m1", "title": "M1", "lessons": [{"id": "c-l1", "title": "One"}]},
            {"id": "m2", "title": "M2", "lessons": [{"id": "c-l3", "title": "Three"}]},
        ]}))
    exams_dir = course / "exams"
    exams_dir.mkdir()
    for key in ("m1", "m2", "final"):
        (exams_dir / f"{key}.json").write_text(json.dumps({"questions": []}))
    revised = _valid_compiled("c")  # keeps only module m1 → m2 is dropped
    out = courses.apply_revision(cdir, "c", revised, now="20260715T120001Z")
    assert out is not None
    assert (exams_dir / "m1.json").exists()
    assert (exams_dir / "final.json").exists()
    assert not (exams_dir / "m2.json").exists()


def test_list_courses_includes_passed_flag(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    summaries = courses.list_courses(conn, root)
    assert summaries and summaries[0]["passed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_courses_api.py tests/test_courses.py -q`
Expected: new tests FAIL (404s where routes don't exist, KeyError on `exams`/`passed`).

- [ ] **Step 3: Add the routes to backend/app.py**

Add `exams` and `spine` to the existing `from backend import ...` line. Insert after the explain route:

```python
    @app.post("/api/courses/<course_id>/exams/<exam_key>")
    def start_exam(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        slots = exams.blueprint(manifest, exam_key)
        if slots is None:
            return jsonify({"error": "exam not found"}), 404
        spine_lessons = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"]
        prompt = exams.exam_prompt(manifest=manifest, exam_key=exam_key,
                                   slots=slots, spine_lessons=spine_lessons)
        try:
            with generation._gen_lock(("exam", course_id, exam_key)):
                obj = claude_client.run_structured(
                    prompt, validate=lambda o: exams.valid_exam(o, slots))
                exam = exams.finalize_exam(obj, slots, exam_key, course_id)
                exams.save_pending(courses.CONTENT_DIR, course_id, exam)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this exam"}), 502
        return jsonify(exams.client_view(exam))

    @app.post("/api/courses/<course_id>/exams/<exam_key>/submit")
    def submit_exam_route(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        answers = body.get("answers")
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        conn = db.get_connection(path)
        try:
            with generation._gen_lock(("exam", course_id, exam_key)):
                result = exams.submit_exam(
                    courses.CONTENT_DIR, conn, course_id, exam_key, answers,
                    manifest=manifest, generate=generate,
                )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade this exam — your answers were not lost, try again"}), 502
        finally:
            conn.close()
        if result is None:
            return jsonify({"error": "no exam in progress — start it again"}), 404
        return jsonify(result)
```

Extend `get_course` (the existing route) — replace its final `return` with:

```python
        conn = db.get_connection(path)
        try:
            m = mastery.lesson_mastery(conn, courses.CONTENT_DIR, course_id)
            ex = exams.exam_status(conn, course_id, manifest)
        finally:
            conn.close()
        return jsonify({**manifest, "mastery": m, "masteryCounts": mastery.mastery_counts(m),
                        "exams": ex, "coursePassed": exams.course_passed(ex, manifest)})
```

(Note: fold `exam_status` into the SAME connection block that already computes mastery — do not open a second connection.)

- [ ] **Step 4: Extend backend/courses.py**

In `list_courses`, inside the `try` block, add the deferred import next to the existing `from backend import srs` and one summary field:

```python
    from backend import exams, srs
```

and in the summary dict:

```python
                "passed": exams.course_passed(
                    exams.exam_status(conn, child.name, manifest), manifest),
```

In `apply_revision`, after the spine prune block, add:

```python
    # Pending exams for modules dropped by the revision are dead — remove them.
    # (Not locked: a concurrent start_exam for a just-dropped module can at worst
    # leave one stale file, which exam_status ignores and the next revision removes.)
    from backend import exams
    module_ids = {m.get("id") for m in revised.get("modules", [])}
    exams.prune_pending(content_dir, course_id, module_ids | {"final"})
```

- [ ] **Step 5: Run the affected tests, then the full suite**

Run: `.venv/bin/pytest tests/test_courses_api.py tests/test_courses.py tests/test_exams.py -q` → PASS.
Run: `.venv/bin/pytest -q` → all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/courses.py tests/test_courses_api.py tests/test_courses.py
git commit -m "feat(exams): start/submit routes, exam status in course payloads, revision pruning"
```

---

### Task 4: frontend data + views

**Files:**
- Create: `frontend/src/views/exam.js`
- Modify: `frontend/src/courses.js` (append), `frontend/src/views/curriculum.js`, `frontend/src/views/home.js`, `frontend/src/views/loading.js`
- Test: create `frontend/tests/exam.test.js`; extend `frontend/tests/views.test.js`, `frontend/tests/courses.test.js`

**Interfaces:**
- Consumes: `GET /api/courses/<id>` now returns `exams` (`{examKey: {attempts, bestScore, passed}}`) and `coursePassed`; course summaries carry `passed`; start returns `{examKey, questions:[{type, prompt, choices?, objectiveText, bloom, lessonId}]}`; submit returns `{score, passed, attempt, perQuestion, weakSpots}`.
- Produces: `startExam({fetch, courseId, examKey})`, `submitExam({fetch, courseId, examKey, answers})` (both return `{error}` on failure); `examHTML(exam, state)`, `examResultHTML(result)`, `examReady(exam, answers)`; `curriculumHTML(manifest, mastery, currentId, exams, coursePassed)` with `[data-exam]` buttons; `EXAM_STAGES`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/exam.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { examHTML, examResultHTML, examReady } from "../src/views/exam.js";

const EXAM = {
  examKey: "m1",
  questions: [
    { type: "mcq", prompt: "<p>Pick <em>one</em></p>", choices: ["<code>a</code>", "b", "c", "d"], objectiveText: "obj1", bloom: "remember", lessonId: "c1-l1" },
    { type: "free", prompt: "<p>Explain</p>", objectiveText: "obj2 <tag>", bloom: "apply", lessonId: "c1-l2" },
  ],
};

test("examHTML renders server-sanitized prompts raw and answers state", () => {
  const html = examHTML({ ...EXAM, title: "Module exam" }, { answers: { 0: 2 }, submitting: false, error: "" });
  assert.ok(html.includes("<p>Pick <em>one</em></p>"));        // raw, not escaped
  assert.ok(html.includes("<code>a</code>"));                   // choice raw
  assert.ok(html.includes('data-q="0"') && html.includes('data-choice="2"'));
  assert.ok(html.includes("selected"));
  assert.ok(html.includes("<textarea"));
  assert.ok(html.includes("disabled"));                          // free unanswered → submit disabled
});

test("examHTML escapes title and error, enables submit when ready", () => {
  const html = examHTML({ ...EXAM, title: "<b>x</b>" }, { answers: { 0: 1, 1: "done" }, submitting: false, error: "<script>e</script>" });
  assert.ok(!html.includes("<b>x</b>") && html.includes("&lt;b&gt;x&lt;/b&gt;"));
  assert.ok(!html.includes("<script>e</script>"));
  assert.ok(!/data-action="submit-exam"[^>]*disabled/.test(html));
});

test("examReady requires every mcq picked and every free non-blank", () => {
  assert.equal(examReady(EXAM, {}), false);
  assert.equal(examReady(EXAM, { 0: 1 }), false);
  assert.equal(examReady(EXAM, { 0: 1, 1: "  " }), false);
  assert.equal(examReady(EXAM, { 0: 1, 1: "ans" }), true);
});

test("examResultHTML shows pass banner, weak spots, and per-question feedback", () => {
  const result = {
    score: 0.85, passed: true, attempt: 2,
    perQuestion: [
      { type: "mcq", prompt: "<p>Q1</p>", choices: ["a", "b"], answer: 0, correct: false, correctIndex: 1, points: 0, objectiveText: "obj1", lessonId: "c1-l1" },
      { type: "free", prompt: "<p>Q2</p>", answer: "mine", verdict: "close", note: "<em>Nearly</em>", points: 0.5, objectiveText: "obj2", lessonId: "c1-l2" },
    ],
    weakSpots: [{ lessonId: "c1-l1", lessonTitle: "Lesson <One>", objectives: ["obj1 & more"] }],
  };
  const html = examResultHTML(result);
  assert.ok(html.includes("85%"));
  assert.ok(/passed/i.test(html));
  assert.ok(html.includes('data-lesson="c1-l1"'));
  assert.ok(html.includes("Lesson &lt;One&gt;"));                // lesson title escaped
  assert.ok(html.includes("obj1 &amp; more"));                   // objective escaped
  assert.ok(html.includes("<em>Nearly</em>"));                   // grader note raw (server-sanitized)
  assert.ok(html.includes('data-action="retake-exam"'));
  assert.ok(html.includes('data-action="back-curriculum"'));
});

test("examResultHTML fail banner names the bar", () => {
  const html = examResultHTML({ score: 0.5, passed: false, attempt: 1, perQuestion: [], weakSpots: [] });
  assert.ok(html.includes("50%") && html.includes("80%"));
});
```

Append to `frontend/tests/views.test.js` (follow its existing import/fixture style):

```js
test("curriculumHTML renders exam rows with status and final row", () => {
  const manifest = { title: "T", modules: [{ id: "m1", title: "M1", lessons: [{ id: "l1", title: "L1" }] }] };
  const exams = { m1: { attempts: 2, bestScore: 0.9, passed: true } };
  const html = curriculumHTML(manifest, {}, null, exams, false);
  assert.ok(html.includes('data-exam="m1"'));
  assert.ok(html.includes("Passed — best 90%"));
  assert.ok(html.includes('data-exam="final"'));
  assert.ok(html.includes("Not taken"));
  const passedHtml = curriculumHTML(manifest, {}, null, exams, true);
  assert.ok(passedHtml.includes("Course passed"));
});

test("curriculumHTML failed exam row shows best score and attempts", () => {
  const manifest = { title: "T", modules: [{ id: "m1", title: "M1", lessons: [{ id: "l1", title: "L1" }] }] };
  const html = curriculumHTML(manifest, {}, null, { m1: { attempts: 1, bestScore: 0.62, passed: false } }, false);
  assert.ok(html.includes("62%") && html.includes("1 attempt"));
});

test("homeHTML shows passed badge on passed courses", () => {
  const courses = [{ id: "c1", title: "T", subtitle: "s", progress: { done: 1, total: 2, pct: 50 }, reviewsDue: 0, passed: true }];
  assert.ok(homeHTML(courses).includes("Passed"));
  courses[0].passed = false;
  assert.ok(!homeHTML(courses).includes("course-passed"));
});
```

Append to `frontend/tests/courses.test.js` (follow its existing fake-fetch style):

```js
test("startExam posts and maps errors", async () => {
  const calls = [];
  const fetch = async (url, opts) => { calls.push([url, opts]); return { ok: true, json: async () => ({ examKey: "m1", questions: [] }) }; };
  const exam = await startExam({ fetch, courseId: "c1", examKey: "m1" });
  assert.equal(calls[0][0], "/api/courses/c1/exams/m1");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(exam.examKey, "m1");
  const failing = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  assert.equal((await startExam({ fetch: failing, courseId: "c1", examKey: "m1" })).error, "boom");
});

test("submitExam posts answers and maps errors", async () => {
  const calls = [];
  const fetch = async (url, opts) => { calls.push([url, opts]); return { ok: true, json: async () => ({ passed: true }) }; };
  const res = await submitExam({ fetch, courseId: "c1", examKey: "final", answers: [1, "a"] });
  assert.equal(calls[0][0], "/api/courses/c1/exams/final/submit");
  assert.deepEqual(JSON.parse(calls[0][1].body), { answers: [1, "a"] });
  assert.equal(res.passed, true);
  const failing = async () => ({ ok: false, json: async () => { throw new Error("no body"); } });
  assert.ok((await submitExam({ fetch: failing, courseId: "c1", examKey: "final", answers: [] })).error);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: new tests FAIL (module not found / function not exported).

- [ ] **Step 3: Create frontend/src/views/exam.js**

```js
import { esc } from "../escape.js";

// Question prompts, choices, and grader notes arrive SERVER-sanitized and render
// raw (client esc() would double-escape). Objective texts, lesson titles, the exam
// title, and error strings are plain text and MUST be escaped here.

export function examReady(exam, answers) {
  return exam.questions.every((q, i) =>
    q.type === "mcq" ? Number.isInteger(answers[i]) : !!(answers[i] || "").trim());
}

function questionBlock(q, i, answers) {
  let body;
  if (q.type === "mcq") {
    body = q.choices
      .map((c, j) => `<button class="exam-choice${answers[i] === j ? " selected" : ""}" data-q="${i}" data-choice="${j}">${c}</button>`)
      .join("");
  } else {
    body = `<textarea class="exam-free" data-q="${i}" rows="4" maxlength="5000" placeholder="Answer in a few sentences…">${esc(answers[i] || "")}</textarea>`;
  }
  return (
    `<div class="exam-q"><div class="exam-qhead">Question ${i + 1}` +
    `<span class="obj-tag">${esc(q.bloom || "")}</span></div>` +
    `<div class="exam-prompt">${q.prompt}</div>${body}</div>`
  );
}

export function examHTML(exam, state) {
  const qs = exam.questions.map((q, i) => questionBlock(q, i, state.answers)).join("");
  const ready = examReady(exam, state.answers) && !state.submitting;
  return (
    `<div class="exam">` +
    `<div class="eyebrow">EXAM</div>` +
    `<h1 class="session-topic">${esc(exam.title || "")}</h1>` +
    `<div class="exam-note">Pass mark: 80%. You can retake with fresh questions anytime.</div>` +
    qs +
    (state.error ? `<div class="exam-error">${esc(state.error)}</div>` : "") +
    `<div class="nav"><button class="btn-primary" data-action="submit-exam"${ready ? "" : " disabled"}>` +
    `${state.submitting ? "Grading…" : "Submit exam"}</button></div>` +
    `</div>`
  );
}

function resultQuestion(q, i) {
  let feedback;
  if (q.type === "mcq") {
    const yours = q.choices[q.answer];
    feedback = q.correct
      ? `<div class="exam-fb good">Correct</div>`
      : `<div class="exam-fb bad">Your answer: ${yours}. Correct answer: ${q.choices[q.correctIndex]}</div>`;
  } else {
    feedback = `<div class="exam-fb ${q.verdict === "correct" ? "good" : q.verdict === "close" ? "mid" : "bad"}">` +
      `<b>${esc(q.verdict)}</b> — ${q.note}</div>`;
  }
  return (
    `<div class="exam-q result"><div class="exam-qhead">Question ${i + 1}` +
    `<span class="exam-pts">${q.points} pt</span></div>` +
    `<div class="exam-prompt">${q.prompt}</div>${feedback}</div>`
  );
}

export function examResultHTML(result) {
  const pct = Math.round(result.score * 100);
  const banner = result.passed
    ? `<div class="exam-banner pass">Passed — ${pct}%</div>`
    : `<div class="exam-banner fail">Not passed — ${pct}% (80% needed)</div>`;
  const weak = (result.weakSpots || [])
    .map((w) =>
      `<div class="weak-spot"><button class="weak-lesson" data-lesson="${esc(w.lessonId)}">${esc(w.lessonTitle)} →</button>` +
      `<ul>${(w.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul></div>`)
    .join("");
  const qs = (result.perQuestion || []).map(resultQuestion).join("");
  return (
    `<div class="exam-result">${banner}` +
    (weak ? `<h2>Focus next on</h2>${weak}` : "") +
    (qs ? `<h2>Question by question</h2>${qs}` : "") +
    `<div class="nav">` +
    `<button class="btn-secondary" data-action="retake-exam">Retake with fresh questions</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
```

- [ ] **Step 4: Extend courses.js, loading.js, curriculum.js, home.js**

Append to `frontend/src/courses.js`:

```js
export async function startExam({ fetch, courseId, examKey }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}`, { method: "POST" });
  if (!resp.ok) {
    let message = "Couldn't prepare the exam right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function submitExam({ fetch, courseId, examKey, answers }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade the exam right now — your answers are still here, try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
```

Append to `frontend/src/views/loading.js`:

```js
export const EXAM_STAGES = [
  "Reading the objectives…",
  "Writing questions that test them…",
  "Setting plausible distractors…",
  "Almost ready…",
];
```

In `frontend/src/views/curriculum.js`, add after `moduleBlock`'s capstone logic a shared row builder, and thread the two new params through (`moduleBlock(module, mastery, currentId, exams)`, `curriculumHTML(manifest, mastery, currentId, exams, coursePassed)`):

```js
function examRow(examKey, exams, label) {
  const s = exams && exams[examKey];
  let badge = `<span class="exam-status">Not taken</span>`;
  if (s && s.passed) {
    badge = `<span class="exam-status passed">Passed — best ${Math.round(s.bestScore * 100)}%</span>`;
  } else if (s && s.attempts) {
    badge = `<span class="exam-status failed">Best ${Math.round(s.bestScore * 100)}% (${s.attempts} attempt${s.attempts === 1 ? "" : "s"})</span>`;
  }
  const cta = s && s.attempts ? "Retake" : "Take exam";
  return (
    `<button class="c-exam" data-exam="${esc(examKey)}">` +
    `<span class="c-etitle">${esc(label)}</span>${badge}` +
    `<span class="c-ecta">${cta} →</span></button>`
  );
}
```

`moduleBlock` returns `...${rows}</div>${capstone}${examRow(module.id, exams, "Module exam")}</section>`. In `curriculumHTML`, after `courseCapstone` add `examRow("final", exams, "Final exam")`, and in the greeting `<span>` prepend `${coursePassed ? '<span class="course-passed">Course passed</span> ' : ""}` before the lesson count.

Existing `views.test.js` curriculum tests call `curriculumHTML` with three args — the new params default to undefined, which renders "Not taken" exam rows. If any existing assertion breaks on the added rows, update that assertion (do not weaken the new behavior).

In `frontend/src/views/home.js`, in `courseCard`, after the title div add:

```js
      ${c.passed ? '<span class="course-passed">Passed</span>' : ""}
```

- [ ] **Step 5: Run tests to verify they pass, then commit**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS (151 existing + new).

```bash
git add frontend/src/views/exam.js frontend/src/courses.js frontend/src/views/loading.js frontend/src/views/curriculum.js frontend/src/views/home.js frontend/tests/exam.test.js frontend/tests/views.test.js frontend/tests/courses.test.js
git commit -m "feat(exams): exam + result views, curriculum exam rows, start/submit client calls"
```

---

### Task 5: app.js wiring + styles

**Files:**
- Modify: `frontend/src/app.js`, `frontend/styles.css`
- Test: `frontend/tests/*` (existing suites must stay green; behavior here is glue verified by the import check + suites)

**Interfaces:**
- Consumes: everything Task 4 produced; existing `pauseTimer`, `startLoading`, `shellHTML`, `showCurriculum`, `openLesson`, `refreshSummary`, `ui.loadSeq` guard pattern.
- Produces: `showExam(examKey)` reachable from curriculum `[data-exam]` buttons.

- [ ] **Step 1: Wire imports and curriculum**

In `frontend/src/app.js`:
- Extend the courses.js import with `startExam, submitExam`; the loading.js import with `EXAM_STAGES`; add `import { examHTML, examResultHTML } from "./views/exam.js";`.
- In `paintCurriculum`, pass the new args: `curriculumHTML(ui.manifest, (ui.manifest && ui.manifest.mastery) || {}, currentLessonId(), ui.manifest && ui.manifest.exams, !!(ui.manifest && ui.manifest.coursePassed))` and add below the capstone binding:

```js
    view.querySelectorAll("[data-exam]").forEach((b) => {
      b.addEventListener("click", () => showExam(b.getAttribute("data-exam")));
    });
```

- [ ] **Step 2: Add the exam flow (place after showCapstone)**

```js
  // ---- summative exams (sub-project C) ----
  function examLabel(examKey) {
    if (examKey === "final") return `Final exam — ${(ui.manifest && ui.manifest.title) || ""}`;
    const mod = ((ui.manifest && ui.manifest.modules) || []).find((m) => m.id === examKey);
    return mod ? `Module exam — ${mod.title}` : "Exam";
  }

  async function showExam(examKey) {
    pauseTimer();
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "exam-loading";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCurriculum);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", EXAM_STAGES);
    const exam = await startExam({ fetch, courseId: ui.courseId, examKey });
    if (ui.screen !== "exam-loading" || ui.loadSeq !== seq) return; // navigated away mid-load
    if (!exam || exam.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((exam && exam.error) || "Couldn't prepare the exam right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
      return;
    }
    ui.screen = "exam";
    ui.examState = { examKey, exam, answers: {}, submitting: false, error: "" };
    paintExam();
  }

  function paintExam() {
    const st = ui.examState;
    const view = root.querySelector("#view");
    view.innerHTML = examHTML({ ...st.exam, title: examLabel(st.examKey) }, st);
    view.querySelectorAll("[data-choice]").forEach((b) => {
      b.addEventListener("click", () => {
        st.answers[Number(b.getAttribute("data-q"))] = Number(b.getAttribute("data-choice"));
        paintExam();
      });
    });
    // Textareas update state without a repaint (a repaint would steal focus on
    // every keystroke); only the submit button's disabled state is refreshed.
    view.querySelectorAll("textarea[data-q]").forEach((t) => {
      t.addEventListener("input", () => {
        st.answers[Number(t.getAttribute("data-q"))] = t.value;
        const btn = view.querySelector('[data-action="submit-exam"]');
        if (btn) btn.disabled = !(examReady(st.exam, st.answers) && !st.submitting);
      });
    });
    const submit = view.querySelector('[data-action="submit-exam"]');
    if (submit) submit.addEventListener("click", submitCurrentExam);
  }

  async function submitCurrentExam() {
    const st = ui.examState;
    if (!st || st.submitting || !examReady(st.exam, st.answers)) return;
    st.submitting = true;
    st.error = "";
    paintExam();
    const answers = st.exam.questions.map((q, i) => (q.type === "mcq" ? st.answers[i] : st.answers[i] || ""));
    const result = await submitExam({ fetch, courseId: ui.courseId, examKey: st.examKey, answers });
    if (ui.screen !== "exam" || ui.examState !== st) return; // navigated away mid-grade
    st.submitting = false;
    if (!result || result.error) {
      st.error = (result && result.error) || "Couldn't grade the exam right now — your answers are still here, try again.";
      paintExam();
      return;
    }
    await refreshSummary(); // exam status + coursePassed changed
    if (ui.screen !== "exam" || ui.examState !== st) return; // navigated away during refresh
    ui.screen = "exam-result";
    const view = root.querySelector("#view");
    view.innerHTML = examResultHTML(result);
    view.querySelectorAll("[data-lesson]").forEach((b) => {
      b.addEventListener("click", () => openLesson(b.getAttribute("data-lesson")));
    });
    view.querySelector('[data-action="retake-exam"]').addEventListener("click", () => showExam(st.examKey));
    view.querySelector('[data-action="back-curriculum"]').addEventListener("click", showCurriculum);
  }
```

Also extend the exam.js import to include `examReady`: `import { examHTML, examResultHTML, examReady } from "./views/exam.js";`

- [ ] **Step 3: Styles**

Append to `frontend/styles.css` (match the file's existing variable names — inspect nearby rules; `--border-field` exists, `--line` does NOT):

```css
/* ---- summative exams ---- */
.c-exam { display: flex; align-items: center; gap: 10px; width: 100%; margin-top: 8px; padding: 10px 12px; border: 1px solid var(--border-field); border-radius: 10px; background: none; cursor: pointer; text-align: left; }
.c-exam .c-etitle { font-weight: 600; }
.c-exam .c-ecta { margin-left: auto; white-space: nowrap; }
.exam-status { font-size: 12px; opacity: 0.8; }
.exam-status.passed { color: var(--ok, #2e7d32); }
.exam-status.failed { color: var(--warn, #b26a00); }
.course-passed { font-size: 12px; font-weight: 600; color: var(--ok, #2e7d32); }
.exam-q { margin: 18px 0; padding-top: 14px; border-top: 1px solid var(--border-field); }
.exam-qhead { display: flex; align-items: center; gap: 8px; font-weight: 600; margin-bottom: 6px; }
.exam-pts { margin-left: auto; font-size: 12px; opacity: 0.7; }
.exam-choice { display: block; width: 100%; margin-top: 6px; padding: 8px 12px; border: 1px solid var(--border-field); border-radius: 8px; background: none; cursor: pointer; text-align: left; }
.exam-choice.selected { border-color: currentColor; font-weight: 600; }
.exam-free { width: 100%; margin-top: 6px; }
.exam-note { font-size: 13px; opacity: 0.75; margin-bottom: 4px; }
.exam-error { margin-top: 10px; color: var(--warn, #b26a00); }
.exam-banner { padding: 12px 16px; border-radius: 10px; font-weight: 700; margin-bottom: 14px; }
.exam-banner.pass { background: rgba(46, 125, 50, 0.12); }
.exam-banner.fail { background: rgba(178, 106, 0, 0.12); }
.weak-spot { margin: 10px 0; }
.weak-lesson { background: none; border: none; padding: 0; cursor: pointer; font-weight: 600; text-decoration: underline; }
.exam-fb { margin-top: 8px; font-size: 14px; }
.exam-fb.good { color: var(--ok, #2e7d32); }
.exam-fb.mid { color: var(--warn, #b26a00); }
```

If the stylesheet already defines success/warning color variables under different names, use those instead of the `var(--ok, ...)`/`var(--warn, ...)` fallbacks — check before pasting.

- [ ] **Step 4: Verify**

Run all three, in order:

```bash
node --test frontend/tests/*.test.js
node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"
.venv/bin/pytest -q
```

Expected: all frontend tests PASS, `imports ok`, all backend tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "feat(exams): exam sitting/result flow in app.js + styles"
```
