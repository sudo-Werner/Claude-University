# Pedagogy Steps Implementation Plan (pre-quiz + explain-it-back)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a required pre-quiz attempt before each new lesson (pretesting effect) and a skippable graded explain-it-back step after the solution (self-explanation/retrieval), per the approved spec `docs/superpowers/specs/2026-07-15-pedagogy-steps-design.md`.

**Architecture:** Backend: the lesson generator gains a `preQuiz` field (check-shaped, same generation call, validated by the existing `valid_check`, sanitized like `checks`), and a new `/explain` route mirrors the existing `/grade` pipeline (`explain_prompt` + `explain_answer`, reusing `valid_grade` and `run_structured`). Frontend: a new `views/prequiz.js` card gates the lesson body via a `lessonState.stage` field; an explain-it-back card renders below the checks after the solution; `courses.js` gains `explainAnswer`.

**Tech Stack:** Flask + SQLite (pytest), plain ES modules (node:test). No new dependencies.

## Global Constraints

- **Never merge to main or push without Werner's explicit approval.** Work on branch `feat/pedagogy-steps` (already created off main). Committing per task on this branch is expected.
- **No emojis anywhere** — code, UI copy, commit messages.
- Backend tests: `.venv/bin/pytest` from repo root (currently 252 passing — must stay green).
- Frontend tests: `node --test frontend/tests/*.test.js` (currently 138 passing — must stay green). NEVER run `node --test frontend/tests/` (bare directory) — it silently runs nothing.
- **Server-side sanitization boundary:** `preQuiz.prompt/explanation/choices` and the explain `note` are sanitized SERVER-side (`sanitize_html`), exactly like `checks` and the grade note — the client renders them raw (matching `views/checks.js` and `gradeBlock`). Learner-typed text rendered back into HTML client-side (the fill answer echo, the explain textarea content) MUST go through `esc()`.
- `state.stage === "prequiz"` renders a reduced lesson screen; `paintLesson` in app.js MUST bind pre-quiz handlers and return early in that stage — the exercise-body selectors (`[data-field="answer"]` etc.) do not exist then and unconditional binding would throw.
- app.js has no unit tests — after any app.js change run `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`.
- Follow existing patterns exactly: routes open `db.get_connection(path)` only when they need the DB (the new `/explain` route does not); error mapping copies the `/grade` route (`ClaudeAuthError` → 503 reauth, `ClaudeError` → 502).

## Design decisions (already made — implement as stated)

- `preQuiz` is REQUIRED by `valid_lesson` (every newly generated or deepened lesson has one). Cached lessons without it skip the pre-quiz client-side; they are never re-validated.
- Pre-quiz shows only when: `lesson.preQuiz` exists AND the lesson id is NOT a key of the course's mastery map AND the lesson is not opened via the review flow. It must be attempted (submit an answer) to unlock the body; feedback + "Start the lesson" appear after the attempt.
- Grading of the pre-quiz is CLIENT-side via the existing `gradeCheck` (answers already ship in lesson JSON for checks — same trust model).
- Events: `prequiz_attempt` payload `{correct: bool, type: "mcq"|"fill"}`; `lesson_explained` payload `{verdict}`. Neither joins the streak/activity whitelists.
- Explain-it-back grades against the lesson body + reference solution only (no manifest objectives lookup — YAGNI).

---

### Task 1: Backend — `preQuiz` in generation

**Files:**
- Modify: `backend/generation.py` (three spots: `valid_lesson`, `lesson_prompt`, the sanitize block in `_generate_and_store_lesson`)
- Test: `tests/test_generation.py` (append; also update existing fixtures that assert `valid_lesson` — they currently lack `preQuiz` and will start failing, which is expected and part of this task)

**Interfaces:**
- Produces: lesson JSON may contain `preQuiz` (one `valid_check`-shaped item); all newly generated lessons will. Task 3/4 consume `lesson.preQuiz` client-side.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generation.py` (it already has lesson fixtures and imports `generation`; follow the file's existing fixture style — there is a helper/constant producing a valid lesson dict; extend a COPY of it in these tests):

```python
def _valid_lesson_base():
    # Build from the file's existing valid-lesson fixture; shown here explicitly
    # so this test is self-contained if the fixture name differs.
    return {
        "id": "c-l1", "courseId": "c", "topic": "T", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "<p>Body</p>", "hintHtml": "h",
        "solutionAns": "a", "solutionNote": "n",
        "checks": [{"type": "fill", "prompt": "q", "answer": "a", "explanation": "e"}],
        "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                    "answer": 0, "explanation": "Because."},
    }


def test_valid_lesson_requires_prequiz():
    lesson = _valid_lesson_base()
    assert generation.valid_lesson(lesson)
    del lesson["preQuiz"]
    assert not generation.valid_lesson(lesson)


def test_valid_lesson_rejects_malformed_prequiz():
    lesson = _valid_lesson_base()
    lesson["preQuiz"] = {"type": "mcq", "prompt": "", "choices": ["A"], "answer": 0, "explanation": "e"}
    assert not generation.valid_lesson(lesson)


def test_lesson_prompt_mentions_prequiz():
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="c-l1", lesson_title="T",
        module_title="M", position=1, total=1,
    )
    assert "preQuiz" in prompt
```

- [ ] **Step 2: Run the generation tests to see the new tests fail (and note which existing tests break)**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: the 3 new tests FAIL. After implementing Step 3, some EXISTING tests that build lessons without `preQuiz` and assert `valid_lesson(...) is True` (or drive `_generate_and_store_lesson` with a fixture lesson) will fail — updating those fixtures to include a valid `preQuiz` item is in scope for this task. Do not weaken any assertion; only add the field to fixtures.

- [ ] **Step 3: Implement**

In `backend/generation.py`:

1. `valid_lesson` — add the requirement after the checks validation:

```python
    if not valid_check(obj.get("preQuiz")):
        return False
    return all(valid_check(c) for c in checks)
```

(`valid_check(None)` is already False via its `isinstance` guard.)

2. `lesson_prompt` — in the JSON-keys section, after the `checks:` item description, add:

```python
        '  preQuiz: ONE warm-up question in the same item format as a check (mcq or fill), '
        "about the lesson's single core idea. The learner answers it BEFORE reading the "
        "lesson, so it must be attemptable with intuition or general prior knowledge — never "
        "require a term, label, or fact that only this lesson introduces. Make mcq "
        "distractors plausible. Its explanation is shown immediately after the attempt as a "
        "one-sentence preview of the key insight.\n"
```

3. Sanitize block in `_generate_and_store_lesson` — right after the existing `checks` sanitize loop, add:

```python
    pq = lesson.get("preQuiz")
    if isinstance(pq, dict):
        for f in ("prompt", "explanation"):
            if isinstance(pq.get(f), str):
                pq[f] = sanitize_html(pq[f])
        if isinstance(pq.get("choices"), list):
            pq["choices"] = [sanitize_html(c) if isinstance(c, str) else c for c in pq["choices"]]
```

- [ ] **Step 4: Run tests until green**

Run: `.venv/bin/pytest tests/test_generation.py -v` — fix any existing fixture that now lacks `preQuiz` by adding a valid item (e.g. the mcq from `_valid_lesson_base`). Then the full suite:

Run: `.venv/bin/pytest`
Expected: all green (252 + 3 new = 255, plus/minus none).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(generation): required preQuiz field on generated lessons (pretesting effect)"
```

---

### Task 2: Backend — explain-it-back grading route

**Files:**
- Modify: `backend/generation.py` (add `explain_prompt` + `explain_answer` next to `grade_prompt`/`grade_answer`), `backend/app.py` (add route after the grade route)
- Test: `tests/test_generation.py`, `tests/test_courses_api.py` (append; mirror the existing grade tests in each — find them with `grep -n "grade" tests/test_courses_api.py`)

**Interfaces:**
- Consumes: `courses.load_lesson`, `valid_grade`, `sanitize_html`, `claude_client.run_structured` (all existing).
- Produces: `POST /api/courses/<cid>/lessons/<lid>/explain` `{explanation}` → 200 `{verdict, note}` | 400 (empty) | 404 (bad ids/missing lesson) | 502/503 (Claude errors, same mapping as `/grade`). Task 5 consumes this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generation.py`:

```python
def test_explain_answer_grades_and_sanitizes(tmp_path):
    import json as _json
    d = tmp_path / "c1" / "lessons"
    d.mkdir(parents=True)
    (d / "c1-l1.json").write_text(_json.dumps({
        "id": "c1-l1", "promptHtml": "<p>Body</p>", "solutionAns": "42", "solutionNote": "why",
    }))
    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"verdict": "close", "note": "Nice <script>alert(1)</script> effort"}
    result = generation.explain_answer(tmp_path, "c1", "c1-l1", "my own words", generate=fake_generate)
    assert result["verdict"] == "close"
    assert "<script>" not in result["note"]
    assert "my own words" in captured["prompt"]
    assert "42" in captured["prompt"]


def test_explain_answer_none_for_missing_lesson(tmp_path):
    assert generation.explain_answer(tmp_path, "c1", "c1-l9", "x", generate=lambda p: {}) is None
```

Append to `tests/test_courses_api.py` (mirroring its existing grade-route tests — same fixture/monkeypatch style):

```python
def test_explain_route_grades_explanation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import json as _json
    d = tmp_path / "c1" / "lessons"
    d.mkdir(parents=True)
    (d / "c1-l1.json").write_text(_json.dumps({
        "id": "c1-l1", "promptHtml": "<p>Body</p>", "solutionAns": "42", "solutionNote": "why",
    }))
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None: {"verdict": "correct", "note": "well put"})
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={"explanation": "because 42"})
    assert resp.status_code == 200
    assert resp.get_json() == {"verdict": "correct", "note": "well put"}


def test_explain_route_requires_explanation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses/c1/lessons/c1-l1/explain", json={})
    assert resp.status_code == 400
```

(If `test_courses_api.py` does not already import `claude_client`, add the import at the top of the file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -v`
Expected: the 4 new tests FAIL (`explain_answer` missing; route 404).

- [ ] **Step 3: Implement**

In `backend/generation.py`, directly below `grade_answer`:

```python
def explain_prompt(*, prompt_html, solution_ans, solution_note, explanation):
    return (
        "You are a warm, honest tutor. The learner just finished a lesson and is explaining "
        "the core idea back in their own words — the strongest form of retrieval practice. "
        "Judge whether their explanation shows real understanding of the core idea. Judge "
        "understanding, not wording, and do not demand completeness of detail.\n\n"
        f"Lesson body (HTML): {prompt_html}\n"
        f"Reference answer: {solution_ans}\n"
        f"Why it is right: {solution_note}\n"
        f"Learner's explanation: {explanation}\n\n"
        "Decide whether the explanation is correct, close (right idea, a gap or error), or "
        "incorrect. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"verdict":"correct"|"close"|"incorrect","note":"<one or two encouraging sentences '
        "addressed to 'you': what your explanation captured, then the single most important "
        'idea it missed or got wrong>"}'
    )


def explain_answer(content_dir, course_id, lesson_id, explanation, *, generate):
    lesson = courses.load_lesson(content_dir, course_id, lesson_id)
    if lesson is None:
        return None
    prompt = explain_prompt(
        prompt_html=lesson.get("promptHtml", ""),
        solution_ans=lesson.get("solutionAns", ""),
        solution_note=lesson.get("solutionNote", ""),
        explanation=explanation,
    )
    result = generate(prompt)
    if not isinstance(result, dict):
        raise claude_client.ClaudeError("explain grader returned a non-dict result")
    return {"verdict": result["verdict"], "note": sanitize_html(result["note"])}
```

In `backend/app.py`, directly after the `grade_lesson` route:

```python
    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/explain")
    def explain_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True) or {}
        explanation = (body.get("explanation") or "").strip()
        if not explanation:
            return jsonify({"error": "explanation is required"}), 400
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_grade)
        try:
            result = generation.explain_answer(
                courses.CONTENT_DIR, course_id, lesson_id, explanation, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not read your explanation"}), 502
        if result is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(result)
```

- [ ] **Step 4: Run tests until green, then the full suite**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -v` then `.venv/bin/pytest`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py backend/app.py tests/test_generation.py tests/test_courses_api.py
git commit -m "feat(api): POST .../explain grades an explain-it-back answer (mirrors /grade)"
```

---

### Task 3: Frontend — pre-quiz card view

**Files:**
- Create: `frontend/src/views/prequiz.js`
- Modify: `frontend/styles.css`
- Test: create `frontend/tests/prequiz.test.js`

**Interfaces:**
- Consumes: `esc` from `../escape.js`. `preQuiz` item shape (server-sanitized `prompt`/`choices`/`explanation`; render them raw like `views/checks.js` does).
- Produces: `preQuizHTML(preQuiz, state) -> string` where `state.preQuiz` is `undefined` before the attempt or `{answer, result: {correct}}` after. Buttons/inputs use `data-pq-choice="<j>"`, `data-pq-input`, `data-action="pq-submit"`, `data-action="pq-continue"`. Task 4 binds these in app.js.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/prequiz.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { preQuizHTML } from "../src/views/prequiz.js";

const MCQ = { type: "mcq", prompt: "Best guess?", choices: ["A", "B"], answer: 1, explanation: "B because." };
const FILL = { type: "fill", prompt: "Name it", answer: "x", explanation: "It is x." };

test("prequiz mcq renders choices and no feedback before the attempt", () => {
  const html = preQuizHTML(MCQ, {});
  assert.match(html, /BEFORE YOU START/);
  assert.match(html, /Best guess\?/);
  assert.match(html, /data-pq-choice="0"/);
  assert.match(html, /data-pq-choice="1"/);
  assert.doesNotMatch(html, /pq-continue/);
});

test("prequiz mcq after attempt marks correct/wrong, shows explanation and continue", () => {
  const html = preQuizHTML(MCQ, { preQuiz: { answer: 0, result: { correct: false } } });
  assert.match(html, /choice correct/);
  assert.match(html, /choice wrong/);
  assert.match(html, /B because\./);
  assert.match(html, /data-action="pq-continue"/);
  assert.match(html, /disabled/);
});

test("prequiz fill renders input then echoes the escaped answer", () => {
  const before = preQuizHTML(FILL, {});
  assert.match(before, /data-pq-input/);
  assert.match(before, /data-action="pq-submit"/);
  const after = preQuizHTML(FILL, { preQuiz: { answer: "<b>me</b>", result: { correct: true } } });
  assert.doesNotMatch(after, /<b>me<\/b>/);
  assert.match(after, /&lt;b&gt;me&lt;\/b&gt;/);
  assert.match(after, /It is x\./);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the 3 new tests FAIL (module missing); 138 existing pass.

- [ ] **Step 3: Implement**

Create `frontend/src/views/prequiz.js`:

```js
import { esc } from "../escape.js";

// The warm-up attempt before a first-time lesson. preQuiz prompt/choices/explanation
// are server-sanitized (same boundary as checks) — rendered raw, like views/checks.js.
export function preQuizHTML(preQuiz, state) {
  const pq = state.preQuiz || null;
  const answered = !!(pq && pq.result);
  let body;
  if (preQuiz.type === "mcq") {
    body = preQuiz.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === preQuiz.answer) cls = "choice correct";
          else if (j === Number(pq.answer)) cls = "choice wrong";
        }
        return `<button class="${cls}" data-pq-choice="${j}"${answered ? " disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(pq.answer != null ? pq.answer : "")}</b></div>`
      : `<div class="fill-row"><input data-pq-input placeholder="Your best guess…"><button class="btn-secondary" data-action="pq-submit">Submit</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${pq.result.correct ? "ok" : "no"}">${pq.result.correct ? "Correct" : "Not quite"} — ${preQuiz.explanation}</div>` +
      `<button class="btn-primary" data-action="pq-continue" style="margin-top:12px">Start the lesson</button>`
    : "";
  return (
    `<section class="card prequiz"><span class="eyebrow">BEFORE YOU START</span>` +
    `<div class="pq-lead">Take your best guess — attempting first makes the lesson stick, even if you get it wrong.</div>` +
    `<div class="check-q">${preQuiz.prompt}</div>${body}${feedback}</section>`
  );
}
```

In `frontend/styles.css`, near the checks styles add:

```css
.prequiz{margin-top:14px}
.pq-lead{color:var(--text-dim); font-size:14px; margin:8px 0 12px}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test frontend/tests/*.test.js`
Expected: all green (141).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/prequiz.js frontend/styles.css frontend/tests/prequiz.test.js
git commit -m "feat(prequiz): pre-quiz card view (attempt-gated, reuses check styling)"
```

---

### Task 4: Frontend — pre-quiz flow wiring (stage-gated lesson)

**Files:**
- Modify: `frontend/src/views/lesson.js`, `frontend/src/app.js`
- Test: `frontend/tests/views.test.js` (append)

**Interfaces:**
- Consumes: `preQuizHTML` (Task 3), `gradeCheck` from `views/checks.js` (already imported in app.js), lesson field `preQuiz` (Task 1).
- Produces: `lessonHTML` renders the pre-quiz screen when `state.stage === "prequiz"`; app.js sets `stage` on every lesson-open path and logs `prequiz_attempt`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/views.test.js` (SAMPLE_LESSON is an existing fixture in that file):

```js
test("lessonHTML renders the pre-quiz stage instead of the exercise", () => {
  const lesson = { ...SAMPLE_LESSON, preQuiz: { type: "mcq", prompt: "Guess?", choices: ["A", "B"], answer: 0, explanation: "A." } };
  const html = lessonHTML(lesson, { stage: "prequiz", answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.match(html, /BEFORE YOU START/);
  assert.doesNotMatch(html, /data-field="answer"/);
  assert.doesNotMatch(html, /reveal-solution/);
});

test("lessonHTML renders the exercise when stage is main or unset", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.match(html, /data-field="answer"/);
  assert.doesNotMatch(html, /BEFORE YOU START/);
});
```

(If `views.test.js` calls `lessonHTML` with a state fixture object, reuse that object spread with `stage`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the first new test FAILS (no pre-quiz stage); the second passes already — keep it as the regression pin.

- [ ] **Step 3: Implement the view gate**

In `frontend/src/views/lesson.js`:
1. Add `import { preQuizHTML } from "./prequiz.js";`
2. In `lessonHTML`, after the `segs` computation and BEFORE `sol`/`hint` are computed, add the stage gate (it reuses the same header/player-nav markup — extract nothing; duplicate the small header block inline to keep the exercise path untouched):

```js
  if (state.stage === "prequiz" && lesson.preQuiz) {
    return `
    <div class="lesson-col">
    <div class="lesson-head">
    <div>
      <div class="steps">${segs}</div>
      <div class="steprow"><span>Step ${lesson.step} of ${lesson.totalSteps} · <b>Warm-up</b></span><span class="right">${lesson.topic}</span></div>
    </div>
      <div class="player-nav">
        <button class="pn-btn pn-curric" data-action="curriculum">${LIST}<span>Curriculum</span></button>
        <div class="pn-move">
          <button class="pn-btn" data-action="prev-lesson" aria-label="Previous lesson"${nav.hasPrev ? "" : " disabled"}>‹</button>
          <button class="pn-btn" data-action="next-lesson" aria-label="Next lesson"${nav.hasNext ? "" : " disabled"}>›</button>
        </div>
      </div>
    </div>
    ${preQuizHTML(lesson.preQuiz, state)}
    </div>
  `;
  }
```

- [ ] **Step 4: Wire app.js**

In `frontend/src/app.js`:

1. In `openLesson`, after the `ui.lessonState = { ... }` reset line, add:

```js
    const completed = !!(ui.manifest && ui.manifest.mastery && ui.manifest.mastery[lessonId]);
    ui.lessonState.stage = ui.lesson.preQuiz && !completed ? "prequiz" : "main";
```

2. In `startReviewSession` and in the review-queue branch of `advanceAfterLesson`, add `stage: "main"` to the `ui.lessonState = { ... }` object literals (reviews never pre-quiz). Also add `stage: "main"` to the reset in `deepenCurrentLesson` (the learner is already inside the lesson).

3. In `paintLesson`, restructure the top so the pre-quiz stage binds only what exists, then returns:

```js
  function paintLesson() {
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    const curBtn = view.querySelector('[data-action="curriculum"]');
    if (curBtn) curBtn.addEventListener("click", showCurriculum);
    const prevBtn = view.querySelector('[data-action="prev-lesson"]');
    if (prevBtn) prevBtn.addEventListener("click", () => { const a = adjacentLesson(-1); if (a) openLesson(a.id); });
    const nextBtn = view.querySelector('[data-action="next-lesson"]');
    if (nextBtn) nextBtn.addEventListener("click", () => { const a = adjacentLesson(1); if (a) openLesson(a.id); });
    if (ui.lessonState.stage === "prequiz") { bindPreQuiz(view); return; }
    ...existing bindings unchanged, minus the now-hoisted curriculum/prev/next bindings...
  }
```

(Remove the original `curBtn`/`prevBtn`/`nextBtn` bindings from lower in the function so they are not bound twice.)

4. Add `bindPreQuiz` next to `paintLesson`:

```js
  function answerPreQuiz(answer) {
    if (ui.lessonState.preQuiz && ui.lessonState.preQuiz.result) return; // already attempted
    const result = gradeCheck(ui.lesson.preQuiz, answer);
    ui.lessonState.preQuiz = { answer, result };
    log("prequiz_attempt", {
      courseId: ui.courseId, topicId: ui.lesson.id,
      payload: { correct: result.correct, type: ui.lesson.preQuiz.type },
    });
    paintLesson();
  }

  function bindPreQuiz(view) {
    view.querySelectorAll("[data-pq-choice]").forEach((btn) => {
      btn.addEventListener("click", () => answerPreQuiz(Number(btn.getAttribute("data-pq-choice"))));
    });
    const submit = view.querySelector('[data-action="pq-submit"]');
    if (submit) submit.addEventListener("click", () => {
      const inp = view.querySelector("[data-pq-input]");
      const val = inp ? inp.value.trim() : "";
      if (!val) return;
      answerPreQuiz(val);
    });
    const cont = view.querySelector('[data-action="pq-continue"]');
    if (cont) cont.addEventListener("click", () => { ui.lessonState.stage = "main"; paintLesson(); });
  }
```

- [ ] **Step 5: Run tests + import check**

Run: `node --test frontend/tests/*.test.js` — all green.
Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` — `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/lesson.js frontend/src/app.js frontend/tests/views.test.js
git commit -m "feat(lesson): stage-gated pre-quiz before first-time lessons"
```

---

### Task 5: Frontend — explain-it-back card

**Files:**
- Modify: `frontend/src/views/lesson.js`, `frontend/src/courses.js`, `frontend/src/app.js`, `frontend/styles.css`
- Test: `frontend/tests/views.test.js`, `frontend/tests/courses.test.js` (append)

**Interfaces:**
- Consumes: `POST .../explain` (Task 2). `state.explain = {text, grading, grade}`.
- Produces: `explainAnswer({fetch, courseId, lessonId, explanation})` in courses.js; an explain card in `lessonHTML` rendered only when `state.solutionRevealed`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/views.test.js`:

```js
test("lessonHTML shows the explain-it-back card only after the solution", () => {
  const hidden = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.doesNotMatch(hidden, /Explain it back/);
  const shown = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true }, {});
  assert.match(shown, /Explain it back/);
  assert.match(shown, /data-field="explain"/);
  assert.match(shown, /data-action="explain-grade"/);
});

test("explain card escapes the learner's text and shows the graded note raw", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    explain: { text: "<b>me</b>", grade: { verdict: "close", note: "Good <em>start</em>" } },
  }, {});
  assert.doesNotMatch(html, /<b>me<\/b>/);
  assert.match(html, /&lt;b&gt;me&lt;\/b&gt;/);
  assert.match(html, /Good <em>start<\/em>/);
  assert.match(html, /Almost there/);
});
```

Append to `frontend/tests/courses.test.js` (mirror its existing gradeAnswer tests):

```js
test("explainAnswer posts the explanation and returns the verdict", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, opts }; return { ok: true, json: async () => ({ verdict: "correct", note: "n" }) }; };
  const out = await explainAnswer({ fetch, courseId: "c1", lessonId: "c1-l1", explanation: "words" });
  assert.equal(out.verdict, "correct");
  assert.equal(sent.url, "/api/courses/c1/lessons/c1-l1/explain");
  assert.equal(JSON.parse(sent.opts.body).explanation, "words");
});

test("explainAnswer surfaces the server error message", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  const out = await explainAnswer({ fetch, courseId: "c1", lessonId: "c1-l1", explanation: "w" });
  assert.equal(out.error, "boom");
});
```

(Add `explainAnswer` to that test file's import from `../src/courses.js`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the 4 new tests FAIL.

- [ ] **Step 3: Implement**

In `frontend/src/courses.js`, after `gradeAnswer`:

```js
export async function explainAnswer({ fetch, courseId, lessonId, explanation }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ explanation }),
  });
  if (!resp.ok) {
    let message = "Couldn't read your explanation right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
```

In `frontend/src/views/lesson.js`, add below `gradeBlock` (reusing `GRADE_LABEL` and the grade CSS classes):

```js
// Explain-it-back (skippable): the learner restates the core idea in their own
// words after the solution; Claude grades understanding via the /explain route.
function explainHTML(state) {
  const ex = state.explain || {};
  const g = ex.grade;
  let result = "";
  if (ex.grading) {
    result = `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Reading your explanation…</span></div>`;
  } else if (g && g.error) {
    result = `<div class="grade grade-soft">${esc(g.error)}</div>`;
  } else if (g) {
    const v = GRADE_LABEL[g.verdict] ? g.verdict : "close";
    result = `<div class="grade grade-${v}" aria-live="polite"><div class="grade-verdict">${GRADE_LABEL[v]}</div><div class="grade-note">${g.note || ""}</div></div>`;
  }
  const canSend = (ex.text || "").trim() && !ex.grading;
  return (
    `<section class="card explain"><div class="checks-title">Explain it back</div>` +
    `<div class="pq-lead">In your own words, what is the core idea of this lesson? Optional — but saying it yourself is the strongest test.</div>` +
    `<textarea data-field="explain" placeholder="The core idea is…">${esc(ex.text || "")}</textarea>` +
    `<button class="btn-secondary" data-action="explain-grade"${canSend ? "" : " disabled"}>${g && !g.error ? "Get feedback again" : "Get feedback"}</button>` +
    `${result}</section>`
  );
}
```

In `lessonHTML`, change the checks line to also render the explain card:

```js
    ${state.solutionRevealed ? checksHTML(lesson.checks || [], state) : ""}
    ${state.solutionRevealed ? explainHTML(state) : ""}
```

In `frontend/src/app.js`:
1. Extend the courses.js import with `explainAnswer`.
2. In `paintLesson` (the main-stage section), add bindings following the check-answer pattern exactly (capture `lessonState`, guard after await):

```js
    const exTa = view.querySelector('[data-field="explain"]');
    if (exTa) exTa.addEventListener("input", () => {
      ui.lessonState.explain = ui.lessonState.explain || {};
      ui.lessonState.explain.text = exTa.value;
      const b = view.querySelector('[data-action="explain-grade"]');
      if (b) b.disabled = !exTa.value.trim() || !!ui.lessonState.explain.grading;
    });
    const exBtn = view.querySelector('[data-action="explain-grade"]');
    if (exBtn) exBtn.addEventListener("click", async () => {
      const ex = ui.lessonState.explain || {};
      const text = (ex.text || "").trim();
      if (!text || ex.grading) return;
      ui.lessonState.explain = { ...ex, grading: true };
      paintLesson();
      const lessonState = ui.lessonState;
      const grade = await explainAnswer({ fetch, courseId: ui.courseId, lessonId: ui.lesson.id, explanation: text });
      if (ui.lessonState !== lessonState || ui.screen !== "lesson") return;
      lessonState.explain = { ...lessonState.explain, grading: false, grade };
      if (grade && !grade.error) {
        log("lesson_explained", { courseId: ui.courseId, topicId: ui.lesson.id, payload: { verdict: grade.verdict } });
      }
      paintLesson();
    });
```

In `frontend/styles.css` (near the checks styles):

```css
.explain{margin-top:14px}
.explain textarea{width:100%; min-height:64px; margin:4px 0 10px}
```

- [ ] **Step 4: Run tests + import check**

Run: `node --test frontend/tests/*.test.js` — all green.
Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` — `imports ok`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/lesson.js frontend/src/courses.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js frontend/tests/courses.test.js
git commit -m "feat(lesson): skippable explain-it-back step graded via /explain"
```
