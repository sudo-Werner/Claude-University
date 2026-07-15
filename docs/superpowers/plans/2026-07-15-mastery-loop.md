# Mastery Loop Implementation Plan (Sub-project D)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Bloom's mastery loop — exam/explain evidence feeds mastery, failure triggers a generated corrective session plus SRS follow-up, the final is earned, and a global transcript records it.

**Architecture:** Everything derives live from the events DB + course manifests (the platform's single-source-of-truth pattern). New module `backend/remediation.py` (corrective sessions persisted under `content/courses/<cid>/remediation/`), new module `backend/transcript.py` (pure assembly), surgical widenings of `mastery.py` / `srs.py` / `stats.py`, two new routes + one 409 gate in `app.py`, and frontend screens for remediation + transcript with soft-gating chips in the curriculum.

**Tech Stack:** Flask + SQLite backend, vanilla ES-module frontend, pytest + node:test.

## Global Constraints

Copied from the spec (`docs/superpowers/specs/2026-07-15-mastery-loop-design.md`) and the codebase conventions — every task's requirements include these:

- **Exam evidence weight:** `mastery.EXAM_WEIGHT = 2.0`; explain verdict points `correct=1.0, close=0.5, incorrect=0.0`; `prequiz_attempt` is EXCLUDED from mastery accuracy (pre-instruction diagnostic).
- **`prequiz_attempt` DOES count toward the streak** (STUDY_EVENTS) but NOT the activity log.
- **Pass bar constants stay untouched:** `exams.PASS_SCORE = 0.8`; never re-derive it.
- **Sanitization boundary (server-sanitizes, client renders raw):** remediation `explanationHtml`, practice `prompt`/`explanation`/`choices` — sanitized with `generation.sanitize_html`, rendered raw client-side. Practice `answer` for fill items is NEVER sanitized (compared verbatim to learner typing). Plain-text fields (lesson titles, objective texts, exam labels, error strings, transcript fields) are `esc()`'d client-side.
- **Remediation file:** `content/courses/<cid>/remediation/<exam_key>.json`, written atomically via `fsutil.write_text_atomic`, stamped with the `attempt` number it remediates; a newer failed attempt regenerates; corrupt file reads as missing. Generation under `generation._gen_lock(("remediation", course_id, exam_key))` in the ROUTE (same pattern as exams).
- **Events are the record:** `remediation_started` (client-logged, `topic_id = exam_key`); practice answers log `lesson_check` with the gap's real `lessonId` as `topic_id` and `payload.source = "remediation"`.
- **Locked final:** start-exam returns **409** for `exam_key == "final"` until every module exam is passed. Nothing else ever locks.
- **Error-mapping convention (copy exactly):** `ClaudeAuthError` → 503 `{"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}`; `ClaudeError` → 502 with a task-specific message. AuthError branch BEFORE ClaudeError (it is a subclass relationship hazard — match existing routes).
- **Test commands:** backend `.venv/bin/pytest` (or targeted `.venv/bin/pytest tests/test_x.py -q`); frontend `node --test frontend/tests/*.test.js` (NEVER the bare directory — it silently runs nothing); after touching `frontend/src/app.js` run `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`.
- **No emojis anywhere.** Match surrounding code style; comments only for non-obvious constraints.
- **`exam_result` payload shape (existing, do not change):** `{score, passed, attempt, perQuestion: [{type, prompt, objectiveText, bloom, lessonId, answer, points, ...}], weakSpots: [{lessonId, lessonTitle, objectives: [str]}]}`.
- Size logic against actual list lengths, never the 10/18 exam constants.

## File Structure

- `backend/mastery.py` — accuracy pool widens (checks + explain + exams)
- `backend/srs.py` — weak-spot due rule (derived, never mutates SM-2)
- `backend/stats.py` — whitelists + exam labels in activity
- `backend/remediation.py` (new) — corrective session: latest-failed lookup, prompt, validation, finalize/sanitize, persistence, prune, ensure
- `backend/transcript.py` (new) — global transcript assembly
- `backend/exams.py` — `final_unlocked` helper
- `backend/app.py` — remediation POST route, transcript GET route, 409 final gate
- `backend/courses.py` — `apply_revision` prunes remediation files
- `frontend/src/views/remediation.js` (new), `frontend/src/views/transcript.js` (new)
- `frontend/src/views/curriculum.js` — final lock row, recommended-next chip, module flags
- `frontend/src/views/exam.js` — "Fix the gaps" button on failed results
- `frontend/src/views/activity.js` — exam/remediation entries
- `frontend/src/views/home.js` — Transcript link
- `frontend/src/views/loading.js` — `REMEDIATION_STAGES`
- `frontend/src/courses.js` — `startRemediation`, `loadTranscript`
- `frontend/src/app.js` — remediation + transcript screens and bindings
- `frontend/styles.css` — gating chips, remediation gaps, transcript record

---

### Task 1: Mastery accuracy pool (explain + exam evidence, prequiz excluded)

**Files:**
- Modify: `backend/mastery.py`
- Test: `tests/test_mastery.py`

**Interfaces:**
- Consumes: existing `events` table rows; `exam_result` payload `perQuestion[].{lessonId, points}`; `lesson_explained` payload `{verdict}`.
- Produces: `mastery._accuracy_pool(conn, course_id) -> {lesson_id: (points, weighted_total)}` (replaces `_checks_by_lesson`); `mastery.EXAM_WEIGHT = 2.0`; `lesson_mastery` and `performance_summary` signatures UNCHANGED (later tasks and existing callers rely on this).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_mastery.py` (it already has `_conn`, `_course`, `_ev` helpers shown below for reference — do not redefine them):

```python
# --- sub-project D: widened accuracy pool ---

def _completed(conn, lesson):
    _ev(conn, "lesson_completed", lesson, {}, "2026-07-10T10:00:00+00:00")


def _exam_ev(conn, exam_key, per_question, occurred="2026-07-12T10:00:00+00:00"):
    payload = {"score": 0.5, "passed": False, "attempt": 1,
               "perQuestion": per_question, "weakSpots": []}
    _ev(conn, "exam_result", exam_key, payload, occurred)


def test_explain_verdicts_join_accuracy_pool(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    _completed(conn, "demo-l1")
    # one wrong check (0/1) + one correct explain (1/1) -> acc 0.5, capped proficient
    _ev(conn, "lesson_check", "demo-l1", {"correct": False}, "2026-07-11T10:00:00+00:00")
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "correct"}, "2026-07-11T10:05:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 2.0)


def test_explain_close_is_half_and_unknown_verdict_ignored(tmp_path):
    conn = _conn()
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "close"}, "2026-07-11T10:00:00+00:00")
    _ev(conn, "lesson_explained", "demo-l1", {"verdict": "banana"}, "2026-07-11T10:01:00+00:00")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (0.5, 1.0)


def test_exam_questions_count_double(tmp_path):
    conn = _conn()
    # one correct check (1/1) + one 0-point exam question at weight 2 -> 1.0/3.0
    _ev(conn, "lesson_check", "demo-l1", {"correct": True}, "2026-07-11T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}])
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 3.0)


def test_exam_partial_points_scale_by_weight(tmp_path):
    conn = _conn()
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.5}])
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (1.0, 2.0)  # 0.5 * EXAM_WEIGHT / EXAM_WEIGHT


def test_prequiz_never_counts(tmp_path):
    conn = _conn()
    _ev(conn, "prequiz_attempt", "demo-l1", {"correct": False, "type": "mcq"},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo") == {}


def test_remediation_checks_count_like_checks(tmp_path):
    conn = _conn()
    _ev(conn, "lesson_check", "demo-l1", {"correct": True, "source": "remediation"},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo")["demo-l1"] == (1.0, 1.0)


def test_exam_evidence_caps_mastery_level(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    _completed(conn, "demo-l1")
    # three good reviews would be "mastered"; an all-wrong exam drags acc to 0 -> attempted
    for d in ("2026-07-01", "2026-07-02", "2026-07-08"):
        _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, f"{d}T10:00:00+00:00")
    _exam_ev(conn, "m1", [{"lessonId": "demo-l1", "points": 0.0}])
    assert mastery.lesson_mastery(conn, root, "demo")["demo-l1"] == "attempted"


def test_malformed_exam_payload_rows_are_skipped(tmp_path):
    conn = _conn()
    _ev(conn, "exam_result", "m1", {"perQuestion": [{"lessonId": "demo-l1", "points": "x"},
                                                    "junk", {"points": 1.0}]},
        "2026-07-11T10:00:00+00:00")
    assert mastery._accuracy_pool(conn, "demo") == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_mastery.py -q`
Expected: FAIL — `AttributeError: module 'backend.mastery' has no attribute '_accuracy_pool'`

- [ ] **Step 3: Implement** — in `backend/mastery.py`, REPLACE the whole `_checks_by_lesson` function with the pool below, and update its two call sites:

```python
# Summative evidence (exam questions) outweighs a formative check; the constant
# is the single tunable knob for that judgment call.
EXAM_WEIGHT = 2.0

_EXPLAIN_POINTS = {"correct": 1.0, "close": 0.5, "incorrect": 0.0}


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
```

In `lesson_mastery`, replace:

```python
    checks = _checks_by_lesson(conn, course_id)
```
with
```python
    pool = _accuracy_pool(conn, course_id)
```
and replace:
```python
        c = checks.get(lid)
        acc = (c[0] / c[1]) if c and c[1] else None
```
with
```python
        p = pool.get(lid)
        acc = (p[0] / p[1]) if p and p[1] else None
```

In `performance_summary`, replace:

```python
    checks = _checks_by_lesson(conn, course_id)
    correct = sum(c for c, _ in checks.values())
    total = sum(t for _, t in checks.values())
```
with
```python
    pool = _accuracy_pool(conn, course_id)
    correct = sum(p for p, _ in pool.values())
    total = sum(t for _, t in pool.values())
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_mastery.py -q`
Expected: ALL PASS (existing tests still green — the check-only behavior is a strict subset).

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest -q` — expected all green.

```bash
git add backend/mastery.py tests/test_mastery.py
git commit -m "feat(mastery): widen accuracy pool to explain-back + exam evidence (prequiz excluded)"
```

---

### Task 2: SRS weak-spot due rule + stats whitelists

**Files:**
- Modify: `backend/srs.py`, `backend/stats.py`
- Test: `tests/test_srs.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: `exam_result` payload `{passed, weakSpots: [{lessonId, ...}]}`.
- Produces: `srs.due_lesson_ids` UNCHANGED signature, now also returns weak-spot-due lessons; `stats.STUDY_EVENTS`/`ACTIVITY_EVENTS` widened; `stats.recent_activity` entries gain `examLabel` (str), `score` (float), `passed` (bool) for exam rows and `examLabel` for `remediation_started` rows. `stats._course_titles` now returns a 3-tuple `(course_title, lesson_titles, module_titles)`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_srs.py` (its `_fixture` builds `root` with course `demo`, lessons `demo-l1`/`demo-l2` — reuse it; check its exact shape in the file before writing):

```python
def _exam_fail(conn, exam_key, weak_lessons, occurred):
    events.insert_events(conn, [{
        "client_event_id": f"exam-{exam_key}-{occurred}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "demo", "topic_id": exam_key,
        "payload": {"score": 0.5, "passed": False, "attempt": 1,
                    "weakSpots": [{"lessonId": l, "lessonTitle": l, "objectives": []}
                                  for l in weak_lessons]},
    }])


def _exam_pass(conn, exam_key, occurred):
    events.insert_events(conn, [{
        "client_event_id": f"examp-{exam_key}-{occurred}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "demo", "topic_id": exam_key,
        "payload": {"score": 0.9, "passed": True, "attempt": 2, "weakSpots": []},
    }])


def test_weak_spot_makes_unreviewed_lesson_due(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-14T10:00:00+00:00")
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15))
    assert due == ["demo-l1"]


def test_review_after_fail_clears_weak_spot(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-10T10:00:00+00:00")
    events.insert_events(conn, [{
        "client_event_id": "r1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-07-12T10:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    # SM-2 next_review = 07-13 which is <= today, so it IS due via SM-2; use a
    # today inside the interval to isolate the weak-spot rule.
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 12))
    assert "demo-l1" not in due


def test_later_pass_clears_weak_spot(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "m1", ["demo-l1"], "2026-07-10T10:00:00+00:00")
    _exam_pass(conn, "m1", "2026-07-14T10:00:00+00:00")
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15)) == []


def test_final_weak_spots_also_count(conn, tmp_path):
    root = _fixture(tmp_path)
    _exam_fail(conn, "final", ["demo-l2"], "2026-07-14T10:00:00+00:00")
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 7, 15)) == ["demo-l2"]
```

Append to `tests/test_stats.py`:

```python
def test_exam_and_prequiz_and_remediation_count_toward_streak(conn):
    events.insert_events(conn, [_ev(1, "exam_result", "2026-07-15T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1
    events.insert_events(conn, [_ev(2, "prequiz_attempt", "2026-07-14T09:00:00+00:00")])
    events.insert_events(conn, [_ev(3, "remediation_started", "2026-07-13T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 3


def test_activity_labels_exam_results(conn, tmp_path):
    root = tmp_path / "courses"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "course.json").write_text(json.dumps({
        "id": "c1", "title": "Algo", "modules": [
            {"id": "m1", "title": "Sorting", "lessons": [{"id": "c1-l1", "title": "L1"}]}],
    }))
    ev = _ev(1, "exam_result", "2026-07-15T09:00:00+00:00", topic_id="m1")
    ev["payload"] = {"score": 0.85, "passed": True, "attempt": 1}
    fv = _ev(2, "exam_result", "2026-07-15T10:00:00+00:00", topic_id="final")
    fv["payload"] = {"score": 0.7, "passed": False, "attempt": 1}
    rv = _ev(3, "remediation_started", "2026-07-15T11:00:00+00:00", topic_id="final")
    events.insert_events(conn, [ev, fv, rv])
    entries = stats.recent_activity(conn, root)
    assert entries[0]["examLabel"] == "Final exam"          # remediation_started
    assert entries[1]["examLabel"] == "Final exam"
    assert entries[1]["score"] == 0.7 and entries[1]["passed"] is False
    assert entries[2]["examLabel"] == "Sorting exam"
    assert entries[2]["passed"] is True
```

(`tests/test_stats.py` `_ev` already accepts `topic_id`; check whether `json` is imported there and add `import json` if missing.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_srs.py tests/test_stats.py -q`
Expected: FAIL (weak-spot lessons not due; whitelist misses; missing examLabel).

- [ ] **Step 3: Implement.** In `backend/srs.py` add after `reviews_by_lesson`:

```python
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
            "date": date,
            "passed": bool(payload.get("passed")),
            "weak": {w.get("lessonId") for w in payload.get("weakSpots") or []
                     if isinstance(w, dict)},
        }
    return latest


def _weak_since_review(lesson_id, module_id, latest_results, last_review):
    """Bloom's corrective follow-up: a lesson flagged weak by the NEWEST result of an
    exam covering it stays due until it is reviewed or a newer attempt passes."""
    for key in (module_id, "final"):
        r = latest_results.get(key)
        if r and not r["passed"] and lesson_id in r["weak"]:
            if last_review is None or r["date"] > last_review:
                return True
    return False
```

REPLACE `due_lesson_ids` with (iterates modules so each lesson knows its module id; SM-2 behavior byte-identical):

```python
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
            last = sched["last_reviewed"] if sched else None
            if _weak_since_review(lid, module.get("id"), latest_results, last):
                due.append(lid)
    return due
```

In `backend/stats.py`, replace the two constants (keep their comments, extend them):

```python
# A streak day is a day the learner actually studied — opened a lesson, completed a
# review, attempted a pre-quiz, sat an exam, or worked a gap review. session_start
# (just opening the app) does not count.
STUDY_EVENTS = ("lesson_view", "lesson_reviewed", "prequiz_attempt",
                "exam_result", "remediation_started")

# Event types worth showing in the study log. Checks, hints, and timer ticks
# are noise at log granularity and are filtered out here, server-side.
ACTIVITY_EVENTS = ("lesson_view", "lesson_reviewed", "course_created", "course_revised",
                   "exam_result", "remediation_started")
```

Extend `_course_titles` to a 3-tuple:

```python
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
```

In `recent_activity`, update the unpacking and entry build:

```python
    for r in rows:
        course_title, lesson_titles, module_titles = (None, {}, {})
        if r["course_id"]:
            course_title, lesson_titles, module_titles = _course_titles(
                content_dir, r["course_id"], cache)
            if course_title is None:
                continue  # course was deleted — stale history is noise in the log
        payload = json.loads(r["payload"]) if r["payload"] else {}
        entry = {
            "occurredAt": r["occurred_at"],
            "type": r["event_type"],
            "courseTitle": course_title,
            "lessonTitle": lesson_titles.get(r["topic_id"]) if r["topic_id"] else None,
            "quality": payload.get("quality"),
        }
        if r["event_type"] in ("exam_result", "remediation_started"):
            key = r["topic_id"]
            entry["examLabel"] = ("Final exam" if key == "final"
                                  else f'{module_titles.get(key, "Module")} exam')
            if r["event_type"] == "exam_result":
                entry["score"] = payload.get("score")
                entry["passed"] = bool(payload.get("passed"))
        out.append(entry)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_srs.py tests/test_stats.py -q` — expected ALL PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest -q` — all green.

```bash
git add backend/srs.py backend/stats.py tests/test_srs.py tests/test_stats.py
git commit -m "feat(loop): weak-spot SRS due rule + exams/prequiz/remediation in stats"
```

---

### Task 3: Remediation backend ("Fix the gaps")

**Files:**
- Create: `backend/remediation.py`
- Modify: `backend/app.py` (one route), `backend/courses.py` (prune in `apply_revision`)
- Test: Create `tests/test_remediation.py`; append route tests to `tests/test_courses_api.py`; append prune test to `tests/test_courses.py`

**Interfaces:**
- Consumes: `generation.sanitize_html`, `generation.valid_check`, `generation._gen_lock`, `fsutil.write_text_atomic`, `spine.load_spine`, `exams._spine_vocab`, `claude_client.run_structured` (two-arg `generate(prompt, validate)` closure, exam-submit pattern).
- Produces (Task 5/6 rely on these): route `POST /api/courses/<course_id>/exams/<exam_key>/remediation` returning the session JSON `{examKey, courseId, attempt, generatedAt, gaps: [{lessonId, lessonTitle, objectives: [str], explanationHtml, practice: [check items]}]}`; module functions `latest_failed_result(conn, course_id, exam_key)`, `remediation_prompt(*, manifest, exam_key, weak_spots, spine_lessons)`, `valid_remediation(obj, weak_spots)`, `finalize_session(obj, weak_spots, exam_key, course_id, attempt)`, `save_session(content_dir, course_id, session)`, `load_session(content_dir, course_id, exam_key)`, `prune(content_dir, course_id, keep_keys)`, `ensure_session(content_dir, course_id, exam_key, failed_payload, *, manifest, spine_lessons, generate)`.

- [ ] **Step 1: Write the module** — create `backend/remediation.py`:

```python
"""Corrective sessions (sub-project D): Bloom's mastery-learning correctives.

A failed exam's weak spots become ONE generated corrective session — each gap
re-explained from a DIFFERENT angle than the lesson took, plus fresh practice
items in the lesson-check shape. Practice grading happens client-side exactly
like lesson checks; answers land as lesson_check events (source="remediation")
so mastery sees them with no new mastery code. The session is persisted per
exam key and stamped with the attempt it remediates: a repeat request re-serves
it free, a newer failed attempt regenerates it.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend import exams, fsutil, generation

PRACTICE_MIN = 2
PRACTICE_MAX = 3


def latest_failed_result(conn, course_id, exam_key):
    """The newest exam_result for this key, if it is a fail with weak spots.
    Returns the payload dict, or None (nothing to remediate)."""
    row = conn.execute(
        "SELECT payload FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ? AND topic_id = ? "
        "ORDER BY occurred_at DESC, id DESC LIMIT 1",
        (course_id, exam_key),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"]) if row["payload"] else {}
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("passed"):
        return None
    weak = [w for w in payload.get("weakSpots") or []
            if isinstance(w, dict) and w.get("lessonId")]
    if not weak:
        return None
    return {**payload, "weakSpots": weak}


def remediation_prompt(*, manifest, exam_key, weak_spots, spine_lessons):
    if exam_key == "final":
        scope = "the course final exam"
    else:
        module = next((m for m in manifest.get("modules", []) if m.get("id") == exam_key), None)
        scope = f'the exam for the module "{(module or {}).get("title", "")}"'
    gap_lines = []
    for i, w in enumerate(weak_spots, start=1):
        objectives = "; ".join(o for o in w.get("objectives", []) if isinstance(o, str))
        gap_lines.append(f'{i}. lessonId={w["lessonId"]} lesson: "{w.get("lessonTitle", "")}" '
                         f"missed objectives: {objectives or w.get('lessonTitle', '')}")
    vocab = exams._spine_vocab([{"lessonId": w["lessonId"]} for w in weak_spots], spine_lessons)
    vocab_block = ("Use EXACTLY this course vocabulary:\n" + "\n".join(vocab) + "\n\n") if vocab else ""
    return (
        f'You are a tutor on a personal learning platform. A learner just failed {scope} '
        f'of the course "{manifest.get("title", "")}" and needs a corrective review of the '
        "gaps below before retaking it.\n"
        f"Course context: {manifest.get('brief', '')}\n"
        + vocab_block +
        "Write EXACTLY one gap review per item below, in the SAME ORDER.\n"
        + "\n".join(gap_lines) + "\n\n"
        "For each gap:\n"
        "- explanationHtml: re-explain the missed objectives from a DIFFERENT angle than a "
        "textbook lesson would — use an analogy, a worked example, or a contrast with a "
        "common misconception. Do NOT summarize the lesson. 2-4 short paragraphs of simple "
        "HTML (p, em, strong, code, ul/ol/li only).\n"
        f"- practice: {PRACTICE_MIN}-{PRACTICE_MAX} NEW retrieval questions on those "
        "objectives (do not reuse exam wording). Each is either "
        '{"type":"mcq","prompt":"...","choices":["..."],"answer":0,"explanation":"..."} '
        "with 3-4 plausible choices and the 0-based correct answer, or "
        '{"type":"fill","prompt":"...","answer":"<the exact word or short phrase>",'
        '"explanation":"..."}. The explanation says why the answer is right.\n'
        "Echo each gap's lessonId verbatim.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"gaps":[{"lessonId":"<from gap>","explanationHtml":"<html>","practice":[...]}]}'
    )


def valid_remediation(obj, weak_spots):
    if not isinstance(obj, dict):
        return False
    gaps = obj.get("gaps")
    if not isinstance(gaps, list) or len(gaps) != len(weak_spots):
        return False
    for g, w in zip(gaps, weak_spots):
        if not isinstance(g, dict) or g.get("lessonId") != w["lessonId"]:
            return False
        if not (isinstance(g.get("explanationHtml"), str) and g["explanationHtml"].strip()):
            return False
        practice = g.get("practice")
        if not (isinstance(practice, list) and PRACTICE_MIN <= len(practice) <= PRACTICE_MAX):
            return False
        if not all(generation.valid_check(p) for p in practice):
            return False
    return True


def finalize_session(obj, weak_spots, exam_key, course_id, attempt):
    """Sanitize learner-visible HTML and stamp gap metadata server-side (titles and
    objectives come from the recorded result, never from the model)."""
    gaps = []
    for g, w in zip(obj["gaps"], weak_spots):
        practice = []
        for p in g["practice"]:
            # Explicit fields only — never carry unknown model keys into stored content.
            item = {"type": p["type"],
                    "prompt": generation.sanitize_html(p["prompt"]),
                    "answer": p["answer"],  # verbatim: fill answers compare to learner typing
                    "explanation": generation.sanitize_html(p["explanation"])}
            if p["type"] == "mcq":
                item["choices"] = [generation.sanitize_html(c) for c in p["choices"]]
            practice.append(item)
        gaps.append({
            "lessonId": w["lessonId"],
            "lessonTitle": w.get("lessonTitle", ""),
            "objectives": [o for o in w.get("objectives", []) if isinstance(o, str)],
            "explanationHtml": generation.sanitize_html(g["explanationHtml"]),
            "practice": practice,
        })
    return {
        "examKey": exam_key,
        "courseId": course_id,
        "attempt": attempt,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gaps": gaps,
    }


def _path(content_dir, course_id, exam_key):
    return Path(content_dir) / course_id / "remediation" / f"{exam_key}.json"


def save_session(content_dir, course_id, session):
    path = _path(content_dir, course_id, session["examKey"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(session, indent=2, ensure_ascii=False))


def load_session(content_dir, course_id, exam_key):
    path = _path(content_dir, course_id, exam_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("gaps"), list) else None


def prune(content_dir, course_id, keep_keys):
    rem_dir = Path(content_dir) / course_id / "remediation"
    if not rem_dir.is_dir():
        return
    for f in rem_dir.glob("*.json"):
        if f.stem not in keep_keys:
            f.unlink(missing_ok=True)


def ensure_session(content_dir, course_id, exam_key, failed_payload, *,
                   manifest, spine_lessons, generate):
    """Serve the stored session when it remediates the latest failed attempt;
    otherwise generate, persist, and return a fresh one."""
    attempt = failed_payload.get("attempt")
    existing = load_session(content_dir, course_id, exam_key)
    if existing is not None and existing.get("attempt") == attempt:
        return existing
    weak_spots = failed_payload["weakSpots"]
    prompt = remediation_prompt(manifest=manifest, exam_key=exam_key,
                                weak_spots=weak_spots, spine_lessons=spine_lessons)
    obj = generate(prompt, lambda o: valid_remediation(o, weak_spots))
    session = finalize_session(obj, weak_spots, exam_key, course_id, attempt)
    save_session(content_dir, course_id, session)
    return session
```

- [ ] **Step 2: Write the failing tests** — create `tests/test_remediation.py`:

```python
import json

from backend import db, events, remediation


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _manifest():
    return {"id": "c1", "title": "Course", "brief": "b", "modules": [
        {"id": "m1", "title": "Mod One", "lessons": [
            {"id": "c1-l1", "title": "L1"}, {"id": "c1-l2", "title": "L2"}]}]}


WEAK = [{"lessonId": "c1-l1", "lessonTitle": "L1", "objectives": ["obj a"]},
        {"lessonId": "c1-l2", "lessonTitle": "L2", "objectives": ["obj b", "obj c"]}]


def _result(conn, exam_key, payload, occurred, i=0):
    events.insert_events(conn, [{
        "client_event_id": f"e-{exam_key}-{occurred}-{i}", "session_id": "s",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "c1", "topic_id": exam_key, "payload": payload,
    }])


def _gaps(weak):
    return {"gaps": [{
        "lessonId": w["lessonId"],
        "explanationHtml": "<p>An analogy.</p>",
        "practice": [
            {"type": "mcq", "prompt": "<p>Q</p>", "choices": ["a", "b", "c"],
             "answer": 1, "explanation": "because"},
            {"type": "fill", "prompt": "Blank?", "answer": "word", "explanation": "why"},
        ],
    } for w in weak]}


def test_latest_failed_result_returns_newest_fail():
    conn = _conn()
    _result(conn, "m1", {"passed": False, "attempt": 1, "weakSpots": WEAK},
            "2026-07-10T10:00:00+00:00")
    _result(conn, "m1", {"passed": False, "attempt": 2, "weakSpots": WEAK[:1]},
            "2026-07-12T10:00:00+00:00")
    got = remediation.latest_failed_result(conn, "c1", "m1")
    assert got["attempt"] == 2 and len(got["weakSpots"]) == 1


def test_latest_failed_result_none_when_latest_passed_or_absent():
    conn = _conn()
    assert remediation.latest_failed_result(conn, "c1", "m1") is None
    _result(conn, "m1", {"passed": False, "attempt": 1, "weakSpots": WEAK},
            "2026-07-10T10:00:00+00:00")
    _result(conn, "m1", {"passed": True, "attempt": 2, "weakSpots": []},
            "2026-07-12T10:00:00+00:00")
    assert remediation.latest_failed_result(conn, "c1", "m1") is None


def test_prompt_names_gaps_and_demands_new_angle():
    p = remediation.remediation_prompt(manifest=_manifest(), exam_key="m1",
                                       weak_spots=WEAK, spine_lessons={})
    assert "lessonId=c1-l1" in p and "obj b; obj c" in p
    assert "DIFFERENT angle" in p and '"gaps"' in p
    assert p.count("lessonId=") == 2


def test_valid_remediation_accepts_good_and_rejects_misaligned():
    good = _gaps(WEAK)
    assert remediation.valid_remediation(good, WEAK)
    swapped = {"gaps": list(reversed(good["gaps"]))}
    assert not remediation.valid_remediation(swapped, WEAK)
    assert not remediation.valid_remediation({"gaps": good["gaps"][:1]}, WEAK)
    one = json.loads(json.dumps(good)); one["gaps"][0]["practice"] = one["gaps"][0]["practice"][:1]
    assert not remediation.valid_remediation(one, WEAK)          # < PRACTICE_MIN
    bad = json.loads(json.dumps(good)); bad["gaps"][0]["practice"][0]["answer"] = 9
    assert not remediation.valid_remediation(bad, WEAK)          # invalid check


def test_finalize_sanitizes_and_stamps_metadata():
    raw = _gaps(WEAK)
    raw["gaps"][0]["explanationHtml"] = '<p onclick="x()">hi</p><script>bad()</script>'
    raw["gaps"][0]["practice"][0]["prompt"] = "<p>Q <script>x</script></p>"
    s = remediation.finalize_session(raw, WEAK, "m1", "c1", 2)
    assert s["attempt"] == 2 and s["examKey"] == "m1"
    assert s["gaps"][0]["lessonTitle"] == "L1" and s["gaps"][0]["objectives"] == ["obj a"]
    assert "<script>" not in s["gaps"][0]["explanationHtml"]
    assert "<p onclick" not in s["gaps"][0]["explanationHtml"]
    assert "<script>" not in s["gaps"][0]["practice"][0]["prompt"]
    assert s["gaps"][0]["practice"][1]["answer"] == "word"       # fill answer untouched


def test_persistence_roundtrip_corrupt_and_prune(tmp_path):
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    assert remediation.load_session(tmp_path, "c1", "m1")["attempt"] == 1
    (tmp_path / "c1" / "remediation" / "m1.json").write_text("{nope")
    assert remediation.load_session(tmp_path, "c1", "m1") is None
    remediation.save_session(tmp_path, "c1", s)
    remediation.save_session(tmp_path, "c1", {**s, "examKey": "final"})
    remediation.prune(tmp_path, "c1", {"final"})
    assert remediation.load_session(tmp_path, "c1", "m1") is None
    assert remediation.load_session(tmp_path, "c1", "final") is not None


def test_ensure_session_reuses_fresh_and_regenerates_stale(tmp_path):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = _gaps(WEAK)
        assert validate(obj)
        return obj

    payload = {"passed": False, "attempt": 1, "weakSpots": WEAK}
    s1 = remediation.ensure_session(tmp_path, "c1", "m1", payload,
                                    manifest=_manifest(), spine_lessons={}, generate=gen)
    assert s1["attempt"] == 1 and len(calls) == 1
    s2 = remediation.ensure_session(tmp_path, "c1", "m1", payload,
                                    manifest=_manifest(), spine_lessons={}, generate=gen)
    assert s2["attempt"] == 1 and len(calls) == 1                 # served from disk
    payload2 = {"passed": False, "attempt": 2, "weakSpots": WEAK[:1]}
    s3 = remediation.ensure_session(tmp_path, "c1", "m1", payload2,
                                    manifest=_manifest(), spine_lessons={},
                                    generate=lambda p, v: _gaps(WEAK[:1]))
    assert s3["attempt"] == 2 and len(s3["gaps"]) == 1            # regenerated
```

- [ ] **Step 3: Run module tests**

Run: `.venv/bin/pytest tests/test_remediation.py -q`
Expected: ALL PASS (module written in Step 1). If any fail, fix the module, not the tests, unless the test contradicts the spec.

- [ ] **Step 4: Add the route.** In `backend/app.py`: extend the import line with `remediation` (`..., exams, spine, remediation`), then add after `submit_exam_route`:

```python
    @app.post("/api/courses/<course_id>/exams/<exam_key>/remediation")
    def start_remediation(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            failed = remediation.latest_failed_result(conn, course_id, exam_key)
        finally:
            conn.close()
        if failed is None:
            return jsonify({"error": "nothing to review — the latest attempt passed"}), 404
        spine_lessons = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"]
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        try:
            with generation._gen_lock(("remediation", course_id, exam_key)):
                session = remediation.ensure_session(
                    courses.CONTENT_DIR, course_id, exam_key, failed,
                    manifest=manifest, spine_lessons=spine_lessons, generate=generate,
                )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare the gap review — try again"}), 502
        return jsonify(session)
```

- [ ] **Step 5: Prune on revision.** In `backend/courses.py` `apply_revision`, change the deferred import block at the tail to:

```python
    # Pending exams and gap reviews for modules dropped by the revision are dead.
    # (Not locked: a concurrent start for a just-dropped module can at worst leave
    # one stale file, which status/freshness checks ignore and the next revision removes.)
    from backend import exams, remediation
    module_ids = {m.get("id") for m in revised.get("modules", [])}
    exams.prune_pending(content_dir, course_id, module_ids | {"final"})
    remediation.prune(content_dir, course_id, module_ids | {"final"})
    return revised
```

(Replace the existing comment + `from backend import exams` + prune + return lines.)

- [ ] **Step 6: Route + prune tests.** Append to `tests/test_courses_api.py` (uses its existing `_client` and `_fixture_course`; course ids come from `manifest["id"]`, never hard-coded):

```python
def _post_exam_result(client, course_id, exam_key, payload, i=0):
    r = client.post("/api/events", json={"events": [{
        "client_event_id": f"x-{exam_key}-{i}", "session_id": "s1",
        "event_type": "exam_result", "occurred_at": f"2026-07-1{i}T10:00:00+00:00",
        "course_id": course_id, "topic_id": exam_key, "payload": payload,
    }]})
    assert r.status_code == 200


def test_remediation_404_without_failed_exam(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, _ = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 404


def test_remediation_generates_serves_and_reuses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["Calculate X"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 1, "weakSpots": weak})
    gaps = {"gaps": [{"lessonId": lesson_id, "explanationHtml": "<p>angle</p>",
                      "practice": [
                          {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                           "answer": 0, "explanation": "e"},
                          {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
                      ]}]}
    calls = []

    def fake_run(prompt, validate=None, **kw):
        calls.append(prompt)
        assert validate(gaps)
        return gaps

    monkeypatch.setattr(claude_client, "run_structured", fake_run)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 200
    body = r.get_json()
    assert body["attempt"] == 1 and body["gaps"][0]["lessonTitle"] == "A"
    assert (tmp_path / cid / "remediation" / "m1.json").exists()
    r2 = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r2.status_code == 200 and len(calls) == 1              # served from disk


def test_remediation_maps_claude_errors(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _post_exam_result(client, cid, "m1", {"score": 0.5, "passed": False, "attempt": 1,
        "weakSpots": [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": []}]})

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("nope")

    monkeypatch.setattr(claude_client, "run_structured", boom)
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation")
    assert r.status_code == 502
    assert not (tmp_path / cid / "remediation" / "m1.json").exists()
```

Append to `tests/test_courses.py` next to the existing exam-prune test (mirror its fixture usage — read that test first and reuse its course-building helper):

```python
def test_apply_revision_prunes_dropped_module_remediation(tmp_path):
    from backend import courses
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [
            {"id": "m1", "title": "M1", "lessons": [{"id": "c-l1", "title": "One"}]},
            {"id": "m2", "title": "M2", "lessons": [{"id": "c-l3", "title": "Three"}]},
        ]}))
    rem_dir = course / "remediation"
    rem_dir.mkdir()
    for key in ("m1", "m2", "final"):
        (rem_dir / f"{key}.json").write_text(json.dumps({"examKey": key, "gaps": [], "attempt": 1}))
    revised = _valid_compiled("c")  # keeps only module m1 -> m2 is dropped
    out = courses.apply_revision(cdir, "c", revised, now="20260715T120002Z")
    assert out is not None
    assert (rem_dir / "m1.json").exists()
    assert (rem_dir / "final.json").exists()
    assert not (rem_dir / "m2.json").exists()
```

(This mirrors `test_apply_revision_prunes_dropped_module_exams` directly above it in the same file and reuses its `_valid_compiled` helper.)

- [ ] **Step 7: Run to verify pass**

Run: `.venv/bin/pytest tests/test_remediation.py tests/test_courses_api.py tests/test_courses.py -q`
Expected: ALL PASS.

- [ ] **Step 8: Full backend suite, then commit**

Run: `.venv/bin/pytest -q` — all green.

```bash
git add backend/remediation.py backend/app.py backend/courses.py tests/test_remediation.py tests/test_courses_api.py tests/test_courses.py
git commit -m "feat(remediation): generated corrective sessions with persistence, route, and revision pruning"
```

---

### Task 4: Locked final + global transcript backend

**Files:**
- Modify: `backend/exams.py` (`final_unlocked`), `backend/app.py` (409 gate + transcript route)
- Create: `backend/transcript.py`
- Test: append to `tests/test_exams.py`, `tests/test_courses_api.py`; create `tests/test_transcript.py`

**Interfaces:**
- Consumes: `exams.exam_status`, `exams.course_passed`, `mastery.lesson_mastery`, `mastery.mastery_counts`, `courses.load_manifest`, `courses.flatten_lessons`.
- Produces: `exams.final_unlocked(status, manifest) -> bool`; `transcript.course_record(conn, content_dir, course_id, manifest) -> dict`; `transcript.transcript(conn, content_dir) -> list`; routes: 409 on locked final; `GET /api/transcript` → `{"courses": [course_record, ...]}`. Course record shape (Task 5 renders it): `{courseId, title, modules: [{key, title, attempts, bestScore, passed, passedOn}], final: {key, title, attempts, bestScore, passed, passedOn}, coursePassed, passedOn, masteryCounts, lessonsTotal, lessonsCompleted}`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_exams.py`:

```python
def test_final_unlocked_requires_every_module_passed():
    manifest = _manifest()
    locked = {"m1": {"passed": True}}
    assert not exams.final_unlocked(locked, manifest)
    assert not exams.final_unlocked({}, manifest)
    both = {"m1": {"passed": True}, "m2": {"passed": True}}
    assert exams.final_unlocked(both, manifest)
    assert not exams.final_unlocked(both, {"modules": []})
```

Create `tests/test_transcript.py`:

```python
import json

from backend import db, events, transcript


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _course(tmp_path, cid="demo"):
    root = tmp_path / "courses"
    (root / cid / "lessons").mkdir(parents=True)
    (root / cid / "course.json").write_text(json.dumps({
        "id": cid, "title": "Demo", "subtitle": "", "brief": "b",
        "modules": [
            {"id": "m1", "title": "M1", "lessons": [{"id": f"{cid}-l1", "title": "L1"}]},
            {"id": "m2", "title": "M2", "lessons": [{"id": f"{cid}-l2", "title": "L2"}]},
        ],
    }))
    return root


def _result(conn, cid, key, score, passed, occurred, i=0):
    events.insert_events(conn, [{
        "client_event_id": f"t-{key}-{occurred}-{i}", "session_id": "s",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": cid, "topic_id": key,
        "payload": {"score": score, "passed": passed, "attempt": i + 1,
                    "perQuestion": [], "weakSpots": []},
    }])


def test_course_record_assembles_scores_attempts_and_dates(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _result(conn, "demo", "m1", 0.6, False, "2026-07-10T09:00:00+00:00", 0)
    _result(conn, "demo", "m1", 0.9, True, "2026-07-11T09:00:00+00:00", 1)
    rec = transcript.course_record(conn, root, "demo", manifest)
    m1 = rec["modules"][0]
    assert m1["attempts"] == 2 and m1["bestScore"] == 0.9 and m1["passed"]
    assert m1["passedOn"] == "2026-07-11"
    assert rec["modules"][1]["attempts"] == 0 and not rec["modules"][1]["passed"]
    assert rec["final"]["title"] == "Final exam"
    assert not rec["coursePassed"] and rec["passedOn"] is None
    assert rec["lessonsTotal"] == 2 and rec["lessonsCompleted"] == 0


def test_course_record_passed_on_is_latest_first_pass(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _result(conn, "demo", "m1", 0.9, True, "2026-07-10T09:00:00+00:00", 0)
    _result(conn, "demo", "m2", 0.85, True, "2026-07-11T09:00:00+00:00", 0)
    _result(conn, "demo", "final", 0.88, True, "2026-07-12T09:00:00+00:00", 0)
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert rec["coursePassed"] and rec["passedOn"] == "2026-07-12"


def test_transcript_lists_courses_and_skips_malformed(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    (root / "broken").mkdir()
    (root / "broken" / "course.json").write_text("{nope")
    out = transcript.transcript(conn, root)
    assert [c["courseId"] for c in out] == ["demo"]
```

Append to `tests/test_courses_api.py`:

```python
def test_final_locked_until_all_modules_passed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # Stub generation FIRST: if the 409 gate were broken, the route must hit this
    # stub (502), never a real Claude call. 409 vs 502 is the whole assertion.
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    r = client.post(f"/api/courses/{cid}/exams/final")
    assert r.status_code == 409
    for module in manifest["modules"]:
        _post_exam_result(client, cid, module["id"],
                          {"score": 0.9, "passed": True, "attempt": 1, "weakSpots": []}, i=1)
    r2 = client.post(f"/api/courses/{cid}/exams/final")
    assert r2.status_code == 502  # gate opened; generation stub reached


def test_transcript_route_returns_courses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, _ = _fixture_course(courses, tmp_path)
    r = client.get("/api/transcript")
    assert r.status_code == 200
    body = r.get_json()
    assert body["courses"][0]["courseId"] == manifest["id"]
    assert body["courses"][0]["final"]["passed"] is False
```

(If `_fixture_course` has more than one module, pass every module in `test_final_locked_until_all_modules_passed` — read the fixture and post one passing result per module id.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_exams.py tests/test_transcript.py tests/test_courses_api.py -q`
Expected: FAIL — `final_unlocked` missing, `backend.transcript` missing, final route returns 502/200 instead of 409, `/api/transcript` 404.

- [ ] **Step 3: Implement.** In `backend/exams.py` add after `course_passed`:

```python
def final_unlocked(status, manifest):
    """The comprehensive final is earned: it opens only once every module exam
    is passed (mastery-learning gate — the single hard gate in the platform)."""
    modules = manifest.get("modules", [])
    return bool(modules) and all(status.get(m.get("id"), {}).get("passed") for m in modules)
```

Create `backend/transcript.py`:

```python
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
    return {
        "courseId": course_id,
        "title": manifest.get("title", ""),
        "modules": modules,
        "final": row("final", "Final exam"),
        "coursePassed": passed,
        "passedOn": passed_on,
        "masteryCounts": mastery.mastery_counts(m),
        "lessonsTotal": len(courses.flatten_lessons(manifest)),
        "lessonsCompleted": len(m),
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
```

In `backend/app.py`: extend the backend import with `transcript`. In `start_exam`, insert the gate right after the `slots is None` check:

```python
        if exam_key == "final":
            conn = db.get_connection(path)
            try:
                status = exams.exam_status(conn, course_id, manifest)
            finally:
                conn.close()
            if not exams.final_unlocked(status, manifest):
                return jsonify({"error": "The final is locked — pass every module exam first."}), 409
```

Add the transcript route after `get_activity`:

```python
    @app.get("/api/transcript")
    def get_transcript():
        conn = db.get_connection(path)
        try:
            result = transcript.transcript(conn, courses.CONTENT_DIR)
        finally:
            conn.close()
        return jsonify({"courses": result})
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_exams.py tests/test_transcript.py tests/test_courses_api.py -q` — ALL PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest -q` — all green.

```bash
git add backend/exams.py backend/transcript.py backend/app.py tests/test_exams.py tests/test_transcript.py tests/test_courses_api.py
git commit -m "feat(gating): earned final (409 until modules passed) + global transcript route"
```

---

### Task 5: Frontend views + client calls

**Files:**
- Create: `frontend/src/views/remediation.js`, `frontend/src/views/transcript.js`
- Modify: `frontend/src/views/curriculum.js`, `frontend/src/views/exam.js`, `frontend/src/views/activity.js`, `frontend/src/views/home.js`, `frontend/src/views/loading.js`, `frontend/src/courses.js`
- Test: create `frontend/tests/remediation.test.js`, `frontend/tests/transcript.test.js`; append to `frontend/tests/views.test.js`, `frontend/tests/exam.test.js`, `frontend/tests/activity.test.js`, `frontend/tests/home.test.js`, `frontend/tests/courses.test.js`

**Interfaces:**
- Consumes: Task 3's session JSON, Task 4's transcript JSON, existing `esc`, check CSS classes (`check`, `choice`, `fill-row`, `check-feedback`).
- Produces (Task 6 relies on these): `remediationHTML(session, state)` and `flatPractice(session) -> [{gapIndex, lessonId, check}]` from `views/remediation.js` (state = `{answers: {}, results: {}}` keyed by flat index; attributes `data-rq`, `data-rq-choice`, `data-rq-input`, `data-action="rq-fill"`, plus `data-action="retake-exam"` / `"back-curriculum"`); `transcriptHTML(data)`; `REMEDIATION_STAGES`; `startRemediation({fetch, courseId, examKey})`; `loadTranscript({fetch})`; `curriculumHTML` SAME 5-arg signature (gating computed inside); `examResultHTML` adds `data-action="fix-gaps"` when failed with weak spots; `recommendedStep(manifest, mastery, exams)` exported from curriculum.js.

**Escaping boundary in these views:** `explanationHtml`, practice `prompt`/`choices`/`explanation` render RAW (server-sanitized). Lesson titles, objectives, exam labels, transcript titles/dates, error strings → `esc()`.

- [ ] **Step 1: Create `frontend/src/views/remediation.js`:**

```js
import { esc } from "../escape.js";

// A corrective session after a failed exam: per gap, a new-angle explanation
// (server-sanitized, renders raw) plus fresh practice items graded client-side
// exactly like lesson checks. Practice state is keyed by FLAT index across gaps.

export function flatPractice(session) {
  const out = [];
  (session.gaps || []).forEach((g, gi) =>
    (g.practice || []).forEach((check) => out.push({ gapIndex: gi, lessonId: g.lessonId, check })));
  return out;
}

function practiceItem(check, k, state) {
  const result = state.results && state.results[k];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state.answers[k])) cls = "choice wrong";
        }
        return `<button class="${cls}" data-rq="${k}" data-rq-choice="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state.answers && state.answers[k] != null ? state.answers[k] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input data-rq-input="${k}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="rq-fill" data-rq="${k}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}

export function remediationHTML(session, state) {
  let k = 0;
  const gaps = (session.gaps || [])
    .map((g) => {
      const items = (g.practice || []).map((c) => practiceItem(c, k++, state)).join("");
      const objectives = (g.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("");
      return (
        `<section class="rem-gap"><h2>${esc(g.lessonTitle)}</h2>` +
        (objectives ? `<ul class="rem-objectives">${objectives}</ul>` : "") +
        `<div class="rem-explain">${g.explanationHtml}</div>` +
        `<div class="rem-practice">${items}</div></section>`
      );
    })
    .join("");
  return (
    `<div class="remediation">` +
    `<div class="eyebrow">GAP REVIEW</div>` +
    `<h1 class="session-topic">Fix the gaps</h1>` +
    `<div class="exam-note">Each gap is re-explained from a new angle, with fresh practice. ` +
    `When it clicks, retake the exam — new questions, same objectives.</div>` +
    gaps +
    `<div class="nav">` +
    `<button class="btn-primary" data-action="retake-exam">Retake with fresh questions</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
```

- [ ] **Step 2: Create `frontend/src/views/transcript.js`:**

```js
import { esc } from "../escape.js";

// The global academic record. All fields are plain text -> esc() everything.

function pct(score) {
  return `${Math.round((score || 0) * 100)}%`;
}

function examRow(r) {
  let status = `<span class="tr-status">Not taken</span>`;
  if (r.passed) {
    status = `<span class="tr-status passed">${pct(r.bestScore)}` +
      `${r.passedOn ? ` · ${esc(r.passedOn)}` : ""}</span>`;
  } else if (r.attempts) {
    status = `<span class="tr-status failed">best ${pct(r.bestScore)} · ${r.attempts} attempt${r.attempts === 1 ? "" : "s"}</span>`;
  }
  return `<div class="tr-row"><span class="tr-name">${esc(r.title)}</span>${status}</div>`;
}

function courseBlock(c) {
  const rows = (c.modules || []).map(examRow).join("") + examRow(c.final || {});
  const passed = c.coursePassed
    ? `<span class="course-passed">Passed${c.passedOn ? ` — ${esc(c.passedOn)}` : ""}</span>`
    : "";
  const counts = c.masteryCounts || {};
  const mastered = (counts.proficient || 0) + (counts.mastered || 0);
  return (
    `<section class="card tr-course"><div class="tr-chead">` +
    `<h2>${esc(c.title)}</h2>${passed}</div>` +
    `<div class="tr-meta">${c.lessonsCompleted} of ${c.lessonsTotal} lessons studied · ` +
    `${mastered} at proficient or above</div>${rows}</section>`
  );
}

export function transcriptHTML(data) {
  const courses = (data && data.courses) || [];
  const head = `<div class="greeting"><h1>Transcript</h1><span>Your academic record</span></div>`;
  const note = `<div class="tr-note">This transcript records learning on a personal platform. It is not an accredited credential.</div>`;
  if (!courses.length) {
    return `<div class="transcript">${head}` +
      `<div class="card"><div class="prompt">No courses yet — your record will build as you study and sit exams.</div></div>${note}</div>`;
  }
  return `<div class="transcript">${head}${courses.map(courseBlock).join("")}${note}</div>`;
}
```

- [ ] **Step 3: Curriculum gating.** In `frontend/src/views/curriculum.js`:

Add after `moduleProgress`:

```js
// The single "do this next" pointer, in mastery-learning order: finish a module's
// lessons, pass its exam, then move on; the final comes last.
export function recommendedStep(manifest, mastery, exams) {
  for (const mod of manifest.modules || []) {
    for (const l of mod.lessons || []) {
      if (!(mastery && mastery[l.id])) return { type: "lesson", id: l.id };
    }
    const s = exams && exams[mod.id];
    if (!(s && s.passed)) return { type: "exam", id: mod.id };
  }
  const f = exams && exams.final;
  if (!(f && f.passed)) return { type: "exam", id: "final" };
  return null;
}
```

Replace `lessonRow` with (adds the chip):

```js
function lessonRow(lesson, mastery, currentId, recommended) {
  const status = lessonStatus(lesson.id, mastery, currentId);
  const level = mastery && mastery[lesson.id];
  const badge = level ? `<span class="c-badge ${level}">${LABELS[level]}</span>` : "";
  const chip = recommended ? `<span class="c-next">Next</span>` : "";
  const inner = status === "done" ? CHECK : "";
  return (
    `<button class="c-lesson ${status}" data-lesson="${esc(lesson.id)}">` +
    `<span class="c-mark ${status}">${inner}</span>` +
    `<span class="c-ltitle">${esc(lesson.title)}</span>${chip}${badge}</button>`
  );
}
```

Replace `examRow` with (locked + chip variants; old 3-arg calls keep working):

```js
function examRow(examKey, exams, label, opts = {}) {
  const s = exams && exams[examKey];
  if (opts.locked) {
    return (
      `<div class="c-exam locked"><span class="c-etitle">${esc(label)}</span>` +
      `<span class="exam-status">Locked — pass every module exam first</span></div>`
    );
  }
  let badge = `<span class="exam-status">Not taken</span>`;
  if (s && s.passed) {
    badge = `<span class="exam-status passed">Passed — best ${Math.round(s.bestScore * 100)}%</span>`;
  } else if (s && s.attempts) {
    badge = `<span class="exam-status failed">Best ${Math.round(s.bestScore * 100)}% (${s.attempts} attempt${s.attempts === 1 ? "" : "s"})</span>`;
  }
  const chip = opts.recommended ? `<span class="c-next">Next</span>` : "";
  const cta = s && s.attempts ? "Retake" : "Take exam";
  return (
    `<button class="c-exam" data-exam="${esc(examKey)}">` +
    `<span class="c-etitle">${esc(label)}</span>${chip}${badge}` +
    `<span class="c-ecta">${cta} →</span></button>`
  );
}
```

Replace `moduleBlock` with (flag + per-row recommendation):

```js
function moduleBlock(module, mastery, currentId, exams, rec, flagged) {
  const p = moduleProgress(module, mastery);
  const rows = (module.lessons || [])
    .map((l) => lessonRow(l, mastery, currentId,
      !!(rec && rec.type === "lesson" && rec.id === l.id)))
    .join("");
  // #1: once every lesson in the module is done, offer its real-world capstone.
  const complete = p.total > 0 && p.done === p.total;
  const capstone = complete
    ? `<button class="c-capstone" data-capstone="${esc(module.id)}">Real-world connections →</button>`
    : "";
  const flag = flagged ? `<span class="c-mflag">Exam not passed</span>` : "";
  const exam = examRow(module.id, exams, "Module exam",
    { recommended: !!(rec && rec.type === "exam" && rec.id === module.id) });
  return (
    `<section class="c-module">` +
    `<div class="c-mhead"><span class="c-mtitle">${esc(module.title)}</span>${flag}` +
    `<span class="c-mprog">${p.done}/${p.total}</span></div>` +
    `<div class="c-lessons">${rows}</div>${capstone}${exam}</section>`
  );
}
```

Replace `curriculumHTML` with:

```js
export function curriculumHTML(manifest, mastery, currentId, exams, coursePassed) {
  const m = mastery || {};
  const flat = flatten(manifest);
  const done = flat.filter((l) => m[l.id]).length;
  const mods = manifest.modules || [];
  const rec = recommendedStep(manifest, m, exams);
  const passedExam = (id) => !!(exams && exams[id] && exams[id].passed);
  // Soft gating: flag a module you moved beyond without passing its exam.
  const anyDone = mods.map((mod) => (mod.lessons || []).some((l) => m[l.id]));
  const modules = mods
    .map((mod, i) => moduleBlock(mod, m, currentId, exams, rec,
      !passedExam(mod.id) && anyDone.slice(i + 1).some(Boolean)))
    .join("");
  // #1: when the whole course is done, offer a course-wide real-world capstone.
  const courseDone = flat.length > 0 && done === flat.length;
  const courseCapstone = courseDone
    ? `<button class="c-capstone course" data-capstone="course">Real-world connections for the whole course →</button>`
    : "";
  // Hard gate on the final only: it is earned by passing every module exam.
  const finalLocked = mods.length === 0 || !mods.every((mod) => passedExam(mod.id));
  const finalRow = examRow("final", exams, "Final exam",
    { locked: finalLocked, recommended: !!(rec && rec.type === "exam" && rec.id === "final") });
  return (
    `<div class="curriculum">` +
    `<div class="greeting"><h1>${esc(manifest.title)}</h1>` +
    `<span>${coursePassed ? '<span class="course-passed">Course passed</span> ' : ""}${done} of ${flat.length} lessons</span></div>` +
    `${modules}${courseCapstone}${finalRow}</div>`
  );
}
```

- [ ] **Step 4: Smaller view edits.**

`frontend/src/views/exam.js` — in `examResultHTML`, replace the nav block with:

```js
  const fix = !result.passed && (result.weakSpots || []).length
    ? `<button class="btn-primary" data-action="fix-gaps">Fix the gaps</button>`
    : "";
  return (
    `<div class="exam-result">${banner}` +
    (weak ? `<h2>Focus next on</h2>${weak}` : "") +
    (qs ? `<h2>Question by question</h2>${qs}` : "") +
    `<div class="nav">${fix}` +
    `<button class="btn-secondary" data-action="retake-exam">Retake with fresh questions</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
```

`frontend/src/views/activity.js` — at the top of `entryHTML`, add:

```js
  const when = new Date(e.occurredAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (e.type === "exam_result") {
    const pct = Math.round((e.score || 0) * 100);
    return `<div class="act-entry"><span class="act-time">${when}</span>` +
      `<span class="act-text"><b>Exam</b> ${esc(e.examLabel || "")} ` +
      `<span class="act-course">${esc(e.courseTitle || "")}</span>` +
      `<span class="act-quality">${pct}% — ${e.passed ? "passed" : "not passed"}</span></span></div>`;
  }
  if (e.type === "remediation_started") {
    return `<div class="act-entry"><span class="act-time">${when}</span>` +
      `<span class="act-text"><b>Reviewed gaps</b> ${esc(e.examLabel || "")} ` +
      `<span class="act-course">${esc(e.courseTitle || "")}</span></span></div>`;
  }
```

(and remove the now-duplicated `const when` line below).

`frontend/src/views/home.js` — replace the activity button line with:

```js
    <div class="home-links">
    <button class="btn-secondary activity-link" data-action="activity">Recent activity</button>
    <button class="btn-secondary transcript-link" data-action="transcript">Transcript</button>
    </div>
```

`frontend/src/views/loading.js` — add:

```js
export const REMEDIATION_STAGES = [
  "Reading your exam results…",
  "Re-explaining each gap from a new angle…",
  "Writing fresh practice questions…",
  "Almost ready…",
];
```

`frontend/src/courses.js` — append:

```js
export async function startRemediation({ fetch, courseId, examKey }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/remediation`, { method: "POST" });
  if (!resp.ok) {
    let message = "Couldn't prepare the gap review right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function loadTranscript({ fetch }) {
  const resp = await fetch("/api/transcript");
  if (!resp.ok) return null;
  return resp.json();
}
```

- [ ] **Step 5: Write the view tests.**

Create `frontend/tests/remediation.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { remediationHTML, flatPractice } from "../src/views/remediation.js";

const SESSION = {
  examKey: "m1", attempt: 1,
  gaps: [
    { lessonId: "c1-l1", lessonTitle: "Lesson <1>", objectives: ["obj <a>"],
      explanationHtml: "<p>An <em>analogy</em></p>",
      practice: [
        { type: "mcq", prompt: "<p>Pick</p>", choices: ["<code>a</code>", "b"], answer: 0, explanation: "why" },
        { type: "fill", prompt: "Blank?", answer: "w", explanation: "because" },
      ] },
    { lessonId: "c1-l2", lessonTitle: "L2", objectives: [],
      explanationHtml: "<p>Contrast</p>",
      practice: [
        { type: "mcq", prompt: "<p>Q2</p>", choices: ["x", "y"], answer: 1, explanation: "e" },
        { type: "mcq", prompt: "<p>Q3</p>", choices: ["x", "y"], answer: 0, explanation: "e" },
      ] },
  ],
};

test("flatPractice assigns global indices with the right lessonIds", () => {
  const flat = flatPractice(SESSION);
  assert.equal(flat.length, 4);
  assert.equal(flat[0].lessonId, "c1-l1");
  assert.equal(flat[2].lessonId, "c1-l2");
  assert.equal(flat[3].check.prompt, "<p>Q3</p>");
});

test("remediationHTML renders raw explanations, escaped titles, namespaced attrs", () => {
  const html = remediationHTML(SESSION, { answers: {}, results: {} });
  assert.ok(html.includes("<p>An <em>analogy</em></p>"));            // raw
  assert.ok(html.includes("&lt;code&gt;") === false);                 // choices raw
  assert.ok(html.includes("<code>a</code>"));
  assert.ok(html.includes("Lesson &lt;1&gt;"));                       // title escaped
  assert.ok(html.includes("obj &lt;a&gt;"));                          // objective escaped
  assert.ok(html.includes('data-rq="0"') && html.includes('data-rq="3"'));
  assert.ok(html.includes('data-rq-input="1"'));                      // fill at flat index 1
  assert.ok(html.includes('data-action="retake-exam"'));
  assert.ok(html.includes('data-action="back-curriculum"'));
});

test("answered practice shows feedback and disables choices", () => {
  const html = remediationHTML(SESSION, { answers: { 0: 1 }, results: { 0: { correct: false } } });
  assert.ok(html.includes("Not quite"));
  assert.ok(html.includes("choice correct") && html.includes("choice wrong"));
});
```

Create `frontend/tests/transcript.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { transcriptHTML } from "../src/views/transcript.js";

const DATA = { courses: [{
  courseId: "c1", title: "Algo <1>", coursePassed: true, passedOn: "2026-07-12",
  masteryCounts: { attempted: 1, familiar: 0, proficient: 2, mastered: 1 },
  lessonsTotal: 10, lessonsCompleted: 4,
  modules: [
    { key: "m1", title: "Sorting", attempts: 2, bestScore: 0.9, passed: true, passedOn: "2026-07-10" },
    { key: "m2", title: "Graphs", attempts: 1, bestScore: 0.6, passed: false, passedOn: null },
    { key: "m3", title: "DP", attempts: 0, bestScore: 0, passed: false, passedOn: null },
  ],
  final: { key: "final", title: "Final exam", attempts: 1, bestScore: 0.88, passed: true, passedOn: "2026-07-12" },
}] };

test("transcriptHTML renders rows, escapes titles, includes the non-credential note", () => {
  const html = transcriptHTML(DATA);
  assert.ok(html.includes("Algo &lt;1&gt;"));
  assert.ok(html.includes("90%") && html.includes("2026-07-10"));
  assert.ok(html.includes("best 60%") && html.includes("1 attempt"));
  assert.ok(html.includes("Not taken"));
  assert.ok(html.includes("Passed — 2026-07-12"));
  assert.ok(html.includes("4 of 10 lessons studied") && html.includes("3 at proficient or above"));
  assert.ok(html.includes("not an accredited credential"));
});

test("transcriptHTML empty state", () => {
  const html = transcriptHTML({ courses: [] });
  assert.ok(html.includes("No courses yet"));
  assert.ok(html.includes("not an accredited credential"));
});
```

Append to `frontend/tests/views.test.js` (import `recommendedStep` and `curriculumHTML` from `../src/views/curriculum.js` if not already imported; reuse its existing manifest fixture if one exists, else this local one):

```js
const GATE_MANIFEST = {
  title: "T", modules: [
    { id: "m1", title: "M1", lessons: [{ id: "l1", title: "A" }] },
    { id: "m2", title: "M2", lessons: [{ id: "l2", title: "B" }] },
  ],
};

test("recommendedStep walks lessons, then module exam, then final", () => {
  assert.deepEqual(recommendedStep(GATE_MANIFEST, {}, {}), { type: "lesson", id: "l1" });
  assert.deepEqual(recommendedStep(GATE_MANIFEST, { l1: "familiar" }, {}), { type: "exam", id: "m1" });
  const exams = { m1: { passed: true }, m2: { passed: true } };
  assert.deepEqual(
    recommendedStep(GATE_MANIFEST, { l1: "familiar", l2: "familiar" }, exams),
    { type: "exam", id: "final" });
  assert.equal(
    recommendedStep(GATE_MANIFEST, { l1: "familiar", l2: "familiar" }, { ...exams, final: { passed: true } }),
    null);
});

test("curriculum locks the final until every module exam is passed", () => {
  const html = curriculumHTML(GATE_MANIFEST, {}, null, {}, false);
  assert.ok(html.includes("Locked — pass every module exam first"));
  assert.ok(!html.includes('data-exam="final"'));
  const open = curriculumHTML(GATE_MANIFEST, {}, null,
    { m1: { passed: true, bestScore: 0.9, attempts: 1 }, m2: { passed: true, bestScore: 0.9, attempts: 1 } }, false);
  assert.ok(open.includes('data-exam="final"'));
});

test("curriculum flags a module you moved beyond without passing its exam", () => {
  const html = curriculumHTML(GATE_MANIFEST, { l2: "familiar" }, null, {}, false);
  assert.ok(html.includes("Exam not passed"));
  const none = curriculumHTML(GATE_MANIFEST, { l1: "familiar" }, null, {}, false);
  assert.ok(!none.includes("Exam not passed"));
});

test("curriculum marks the recommended next step with a chip", () => {
  const html = curriculumHTML(GATE_MANIFEST, {}, null, {}, false);
  assert.ok(/data-lesson="l1"[^>]*>[\s\S]*?c-next/.test(html.split('data-lesson="l2"')[0]));
});
```

Append to `frontend/tests/exam.test.js`:

```js
test("failed result with weak spots offers Fix the gaps; passed result does not", () => {
  const failed = { score: 0.5, passed: false, weakSpots: [{ lessonId: "l1", lessonTitle: "L", objectives: [] }], perQuestion: [] };
  assert.ok(examResultHTML(failed).includes('data-action="fix-gaps"'));
  const passed = { score: 0.9, passed: true, weakSpots: [], perQuestion: [] };
  assert.ok(!examResultHTML(passed).includes('data-action="fix-gaps"'));
});
```

Append to `frontend/tests/activity.test.js` (match its existing entry-fixture style):

```js
test("activity renders exam and gap-review entries", () => {
  const html = activityHTML([
    { occurredAt: "2026-07-15T09:00:00+00:00", type: "exam_result",
      courseTitle: "Algo", examLabel: "Sorting exam", score: 0.85, passed: true },
    { occurredAt: "2026-07-15T10:00:00+00:00", type: "remediation_started",
      courseTitle: "Algo", examLabel: "Final exam" },
  ], { now: new Date("2026-07-15T12:00:00+00:00") });
  assert.ok(html.includes("Sorting exam") && html.includes("85% — passed"));
  assert.ok(html.includes("Reviewed gaps") && html.includes("Final exam"));
});
```

Append to `frontend/tests/home.test.js`:

```js
test("home shows a transcript link", () => {
  const html = homeHTML([]);
  assert.ok(html.includes('data-action="transcript"'));
});
```

Append to `frontend/tests/courses.test.js` (match its fetch-stub style used for `startExam`):

```js
test("startRemediation maps errors and returns session JSON", async () => {
  const ok = { examKey: "m1", gaps: [] };
  let session = await startRemediation({
    fetch: async () => ({ ok: true, json: async () => ok }), courseId: "c1", examKey: "m1" });
  assert.deepEqual(session, ok);
  session = await startRemediation({
    fetch: async () => ({ ok: false, json: async () => ({ error: "nothing to review" }) }),
    courseId: "c1", examKey: "m1" });
  assert.equal(session.error, "nothing to review");
});

test("loadTranscript returns body or null", async () => {
  const body = { courses: [] };
  assert.deepEqual(await loadTranscript({ fetch: async () => ({ ok: true, json: async () => body }) }), body);
  assert.equal(await loadTranscript({ fetch: async () => ({ ok: false }) }), null);
});
```

- [ ] **Step 6: Run to verify pass**

Run: `node --test frontend/tests/*.test.js`
Expected: ALL PASS (new + existing).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/remediation.js frontend/src/views/transcript.js frontend/src/views/curriculum.js frontend/src/views/exam.js frontend/src/views/activity.js frontend/src/views/home.js frontend/src/views/loading.js frontend/src/courses.js frontend/tests/
git commit -m "feat(views): remediation + transcript views, curriculum soft gating, exam fix-gaps CTA"
```

---

### Task 6: app.js wiring + styles

**Files:**
- Modify: `frontend/src/app.js`, `frontend/styles.css`

**Interfaces:**
- Consumes: everything Task 5 produced; `gradeCheck` from `./views/checks.js` (already imported in app.js).
- Produces: screens `remediation-loading`/`remediation`/`transcript`; bindings for `fix-gaps`, `transcript`, practice grading with `lesson_check` source-tagged events; `remediation_started` logging.

- [ ] **Step 1: Wire app.js.** In `frontend/src/app.js`:

Extend the courses.js import with `startRemediation, loadTranscript`; add imports:

```js
import { remediationHTML, flatPractice } from "./views/remediation.js";
import { transcriptHTML } from "./views/transcript.js";
```

and add `REMEDIATION_STAGES` to the loading.js import list.

Add after `submitCurrentExam` (the exams section):

```js
  // ---- gap review (sub-project D): Bloom's corrective loop after a failed exam ----
  async function showRemediation(examKey) {
    pauseTimer();
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "remediation-loading";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCurriculum);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", REMEDIATION_STAGES);
    const session = await startRemediation({ fetch, courseId: ui.courseId, examKey });
    if (ui.screen !== "remediation-loading" || ui.loadSeq !== seq) return; // navigated away
    if (!session || session.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((session && session.error) || "Couldn't prepare the gap review right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
      return;
    }
    ui.screen = "remediation";
    ui.remState = { examKey, session, items: flatPractice(session), answers: {}, results: {} };
    log("remediation_started", { courseId: ui.courseId, topicId: examKey });
    paintRemediation();
  }

  function paintRemediation() {
    const st = ui.remState;
    const view = root.querySelector("#view");
    view.innerHTML = remediationHTML(st.session, st);
    view.querySelectorAll("[data-rq-choice]").forEach((b) => {
      b.addEventListener("click", () =>
        answerPractice(Number(b.getAttribute("data-rq")), Number(b.getAttribute("data-rq-choice"))));
    });
    view.querySelectorAll('[data-action="rq-fill"]').forEach((b) => {
      b.addEventListener("click", () => {
        const k = Number(b.getAttribute("data-rq"));
        const inp = view.querySelector(`[data-rq-input="${k}"]`);
        answerPractice(k, inp ? inp.value : "");
      });
    });
    view.querySelector('[data-action="retake-exam"]').addEventListener("click", () => showExam(st.examKey));
    view.querySelector('[data-action="back-curriculum"]').addEventListener("click", showCurriculum);
  }

  function answerPractice(k, answer) {
    const st = ui.remState;
    if (!st || st.results[k]) return; // already answered
    const item = st.items[k];
    if (!item) return;
    const result = gradeCheck(item.check, answer);
    st.answers[k] = answer;
    st.results[k] = result;
    // Practice evidence feeds mastery through the same lesson_check pool as lesson
    // checks; the source tag keeps the provenance readable in the event log.
    log("lesson_check", {
      courseId: ui.courseId, topicId: item.lessonId,
      payload: { index: k, type: item.check.type, correct: result.correct, source: "remediation" },
    });
    paintRemediation();
  }

  // ---- transcript (sub-project D): the global academic record ----
  async function showTranscript() {
    pauseTimer();
    ui.screen = "transcript";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Assembling your record…</div></div>`;
    const data = await loadTranscript({ fetch });
    if (ui.screen !== "transcript") return; // navigated away mid-load
    view.innerHTML = transcriptHTML(data || { courses: [] });
  }
```

In `submitCurrentExam`, after the `retake-exam` binding, add:

```js
    const fix = view.querySelector('[data-action="fix-gaps"]');
    if (fix) fix.addEventListener("click", () => showRemediation(st.examKey));
```

In `showHome`, after the activity binding, add:

```js
    const tr = view.querySelector('[data-action="transcript"]');
    if (tr) tr.addEventListener("click", showTranscript);
```

- [ ] **Step 2: Styles.** Append to `frontend/styles.css` (practice items reuse the existing `.check`/`.choice`/`.fill-row`/`.check-feedback` styles — no duplication):

```css
/* ---- mastery loop (sub-project D) ---- */
.c-next { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; color: var(--accent, #7a5c3e); border: 1px solid var(--border-field); border-radius: 999px; padding: 1px 8px; margin-left: 8px; }
.c-mflag { font-size: 11px; color: var(--warn, #b26a00); margin-left: 8px; }
.c-exam.locked { opacity: 0.65; cursor: default; }
.rem-gap { margin: 18px 0; padding: 14px 0 4px; border-top: 1px solid var(--border-field); }
.rem-gap h2 { font-size: 16px; margin: 0 0 6px; }
.rem-objectives { margin: 0 0 8px; padding-left: 18px; color: var(--mut, #8a7d6d); font-size: 13px; }
.rem-explain { font-family: var(--serif); font-size: 16px; line-height: 1.6; color: var(--read); margin: 0 0 10px; }
.home-links { display: flex; gap: 10px; }
.tr-course { margin: 12px 0; }
.tr-chead { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.tr-chead h2 { font-size: 17px; margin: 0; }
.tr-meta { color: var(--mut, #8a7d6d); font-size: 13px; margin: 4px 0 10px; }
.tr-row { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border-field); font-size: 14px; }
.tr-name { color: var(--read); }
.tr-status { color: var(--mut, #8a7d6d); }
.tr-status.passed { color: var(--ok, #2e7d4f); font-weight: 600; }
.tr-status.failed { color: var(--warn, #b26a00); }
.tr-note { color: var(--mut, #8a7d6d); font-size: 12px; margin: 14px 0 4px; }
```

**Before committing:** verify each `var(--x)` used above exists in styles.css (`grep -o -- '--[a-z-]*' frontend/styles.css | sort -u`); where a variable does not exist, keep the fallback value form `var(--x, #hex)` exactly as written (fallbacks above are chosen to match the warm-glass palette), and where it DOES exist drop the fallback to match file style. `.activity-link` may need `margin` adjustments once wrapped in `.home-links` — check how it is currently styled and move any top margin to `.home-links`.

- [ ] **Step 3: Verify**

Run all three:

```bash
node --test frontend/tests/*.test.js
node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"
.venv/bin/pytest -q
```

Expected: frontend suite green, `imports ok`, backend green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "feat(app): gap-review and transcript screens wired, practice feeds mastery"
```

---

## Self-review notes (already applied)

- Spec's GET remediation route dropped as YAGNI (POST re-serves the stored fresh session without a Claude call); spec amended.
- `curriculumHTML` keeps its 5-arg signature — Task 6 needs no paintCurriculum change.
- `_course_titles` 3-tuple: both unpack sites inside `stats.recent_activity` are updated in Task 2 (no other callers exist).
- Practice items reuse `generation.valid_check` (server) and `gradeCheck`/check CSS (client) — one check grammar everywhere.
- `exams._spine_vocab` is reused with minimal slot dicts (`{"lessonId": ...}`) — it reads only that key; same private-reuse precedent as `generation._gen_lock`.
