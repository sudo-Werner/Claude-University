# Checkable Concept-Check Items (Slice 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-graded concept checks (multiple-choice + fill-in-the-blank) to every lesson — generated alongside the exercise, graded with feedback on the lesson screen, and logged as `lesson_check` events.

**Architecture:** Lessons gain a required `checks[]` array in their JSON (generated + validated + sanitized in `backend/generation.py`); a pure `frontend/src/views/checks.js` grades and renders them; `app.js` wires answering, feedback, and `lesson_check` logging into the lesson screen after the solution is revealed. No new endpoint — checks ride inside the existing lesson JSON.

**Tech Stack:** Flask + SQLite, plain ES modules (`node --test`), Playwright for the browser check.

## Global Constraints

- Two check types only: `mcq` (one correct choice, `answer` = integer index) and `fill` (`answer` = string, matched case/space-insensitively). YAGNI on others.
- Checks are **required**: `valid_lesson` requires a `checks` list of **1–3 valid items**; generation retries if Claude omits them.
- Check HTML (`prompt`, `explanation`, `mcq` `choices`) is sanitized with the existing default-deny `sanitize_html` allowlist; user-typed fill answers are HTML-escaped at render.
- `lesson_check` events carry `course_id`, `topic_id`, `payload={index, type, correct}` — reuse the events table, no schema change.
- Testable logic (`valid_check`, `gradeCheck`, `checksHTML`) is pure; `app.js` wiring is browser-verified (Task 4), not unit-tested.
- Deploy via rsync + `systemctl restart claude-university`; verify on the Pi.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure

- `backend/generation.py` (modify) — `lesson_prompt` asks for `checks`; `valid_check`; `valid_lesson` requires checks; `ensure_lesson` sanitizes checks.
- `tests/test_generation.py` (modify) — new check tests; update existing fake-lesson builders to include a valid `checks` (since checks are now required).
- `frontend/src/views/checks.js` (create) — `gradeCheck` + `checksHTML`.
- `frontend/src/views/lesson.js` (modify) — render checks after the solution is revealed.
- `frontend/src/app.js` (modify) — answer/grade/log wiring + lessonState fields.
- `frontend/styles.css` (modify) — check styles.
- Tests: `frontend/tests/checks.test.js` (create).

---

### Task 1: Backend — generate, validate, and sanitize checks

**What / Why / Verify:** Make every generated lesson include valid, sanitized concept checks. *Verify:* `valid_check` accepts good mcq/fill and rejects malformed; `valid_lesson` requires 1–3 checks; `ensure_lesson` sanitizes check HTML; the prompt asks for checks; existing generation tests still pass with checks added.

**Files:**
- Modify: `backend/generation.py`
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `sanitize_html`, `LESSON_KEYS`, `ensure_lesson` (existing).
- Produces: `valid_check(item) -> bool`; `valid_lesson` now also requires `checks` (list, 1–3, each `valid_check`); generated/served lessons carry a sanitized `checks` array of `{type, prompt, explanation, (choices, answer)}`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_generation.py` (and update existing builders per Step 1b):

```python
def test_valid_check_accepts_mcq_and_fill():
    assert gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", "b"], "answer": 1, "explanation": "e"})
    assert gen.valid_check({"type": "fill", "prompt": "p", "answer": "4", "explanation": "e"})


def test_valid_check_rejects_malformed():
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", "b"], "answer": 5, "explanation": "e"})  # index out of range
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a"], "answer": 0, "explanation": "e"})  # <2 choices
    assert not gen.valid_check({"type": "fill", "prompt": "p", "explanation": "e"})  # no answer
    assert not gen.valid_check({"type": "other", "prompt": "p"})
    assert not gen.valid_check("nope")


def test_valid_lesson_requires_checks():
    base = {k: "x" for k in gen.LESSON_KEYS}
    assert not gen.valid_lesson(base)  # no checks
    base["checks"] = []
    assert not gen.valid_lesson(base)  # empty
    base["checks"] = [{"type": "fill", "prompt": "p", "answer": "a", "explanation": "e"}]
    assert gen.valid_lesson(base)
    base["checks"] = [base["checks"][0]] * 4
    assert not gen.valid_lesson(base)  # too many


def test_lesson_prompt_mentions_checks():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    assert "checks" in p
    assert "mcq" in p and "fill" in p


def test_ensure_lesson_sanitizes_check_html(tmp_path):
    import json as _json
    from backend import courses
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(_json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "beginner",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [{"type": "mcq", "prompt": "<img src=x onerror=alert(1)>pick", "choices": ["<b>a</b>", "ok"],
                        "answer": 1, "explanation": "<code>fine</code>"}]
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: made)
    chk = out["checks"][0]
    assert "<img" not in chk["prompt"] and "&lt;img" in chk["prompt"]   # unsafe escaped
    assert "<code>fine</code>" in chk["explanation"]                     # allowlisted kept
    assert "<b>a</b>" not in chk["choices"][0] and "&lt;b&gt;a" in chk["choices"][0]
```

- [ ] **Step 1b: Update the existing fake-lesson tests** — checks are now required, so every existing test that builds a lesson for `valid_lesson`/`ensure_lesson` must include a valid check. In `tests/test_generation.py`, add this module-level constant near the top:

```python
_OK_CHECK = {"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}
```

Then add `"checks": [dict(_OK_CHECK)]` to the lesson dict built in each of these existing tests:
- `test_valid_lesson_requires_all_keys` — the `good = {k: "x" for k in gen.LESSON_KEYS}` dict: set `good["checks"] = [dict(_OK_CHECK)]` before asserting `valid_lesson(good) is True`. (The `missing` case still returns False — leave it.)
- `test_ensure_lesson_generates_validates_and_caches` — the `made = {k: "x" for k in gen.LESSON_KEYS}`: add `made["checks"] = [dict(_OK_CHECK)]`.
- `test_ensure_lesson_reconciles_ids_and_step` — its generated lesson dict: add `["checks"] = [dict(_OK_CHECK)]`.
- `test_ensure_lesson_sanitizes_unsafe_html` — its `made` dict: add `made["checks"] = [dict(_OK_CHECK)]`.

(The `test_ensure_lesson_invalid_generation_raises_and_writes_nothing` and `test_ensure_lesson_unknown_id_returns_none` tests pass an invalid/never-generated lesson and need no change.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: FAIL — `valid_check` missing; `valid_lesson` doesn't require checks; prompt lacks checks; the updated existing tests fail until `valid_lesson` accepts a checks-bearing lesson.

- [ ] **Step 3: Update `backend/generation.py`.**

Add `valid_check` and extend `valid_lesson` (replace the existing `valid_lesson`):
```python
def valid_check(item):
    if not isinstance(item, dict) or not isinstance(item.get("prompt"), str) \
            or not isinstance(item.get("explanation"), str):
        return False
    if item.get("type") == "mcq":
        choices = item.get("choices")
        answer = item.get("answer")
        return (isinstance(choices, list) and len(choices) >= 2
                and isinstance(answer, int) and 0 <= answer < len(choices))
    if item.get("type") == "fill":
        return isinstance(item.get("answer"), str)
    return False


def valid_lesson(obj):
    if not (isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)):
        return False
    checks = obj.get("checks")
    if not (isinstance(checks, list) and 1 <= len(checks) <= 3):
        return False
    return all(valid_check(c) for c in checks)
```

Append the checks instruction to `lesson_prompt`'s returned string (add before the final
`"Shape every learner-facing field..."` line):
```python
        "  checks: a list of 2-3 concept-check items. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,"explanation":"<one sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact expected answer>",'
        '"explanation":"<one sentence why>"}.\n'
```

In `ensure_lesson`, sanitize the checks before the `valid_lesson` call — add this block right
after the existing `for field in ("topic", "eyebrow")` loop and before `if not valid_lesson(lesson)`:
```python
    if isinstance(lesson, dict) and isinstance(lesson.get("checks"), list):
        for chk in lesson["checks"]:
            if not isinstance(chk, dict):
                continue
            for f in ("prompt", "explanation"):
                if isinstance(chk.get(f), str):
                    chk[f] = sanitize_html(chk[f])
            if isinstance(chk.get("choices"), list):
                chk["choices"] = [sanitize_html(c) if isinstance(c, str) else c for c in chk["choices"]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_generation.py -v` then `.venv/bin/pytest -q`
Expected: PASS (all generation tests incl. the new + updated ones; whole backend green).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(backend): required concept-check items in generated lessons (validate + sanitize)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend — `checks.js` grading + rendering

**What / Why / Verify:** The pure check logic. *Verify:* `gradeCheck` grades mcq by index and fill by normalized string; `checksHTML` renders choice buttons / a fill input and shows the explanation + marker once a result exists.

**Files:**
- Create: `frontend/src/views/checks.js`
- Test: `frontend/tests/checks.test.js`

**Interfaces:**
- Produces:
  - `gradeCheck(check, answer) -> { correct: boolean, explanation: string }` — `mcq`: `Number(answer) === check.answer`; `fill`: `normalize(answer) === normalize(check.answer)`, `normalize = (s) => String(s).trim().toLowerCase()`.
  - `checksHTML(checks, state) -> string` — `state.checkAnswers` (per-index entered value) and `state.checkResults` (per-index `{correct}`); renders nothing for an empty/missing `checks`.

- [ ] **Step 1: Write the failing test** `frontend/tests/checks.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { gradeCheck, checksHTML } from "../src/views/checks.js";

test("gradeCheck mcq compares the selected index", () => {
  const c = { type: "mcq", choices: ["a", "b"], answer: 1, explanation: "why" };
  assert.equal(gradeCheck(c, 1).correct, true);
  assert.equal(gradeCheck(c, 0).correct, false);
  assert.equal(gradeCheck(c, "1").correct, true); // string index from the DOM
});

test("gradeCheck fill matches case/space-insensitively", () => {
  const c = { type: "fill", answer: "Four", explanation: "why" };
  assert.equal(gradeCheck(c, "  four ").correct, true);
  assert.equal(gradeCheck(c, "five").correct, false);
});

test("checksHTML renders mcq choices and a fill input", () => {
  const html = checksHTML(
    [{ type: "mcq", prompt: "pick", choices: ["a", "b"], answer: 0, explanation: "e" },
     { type: "fill", prompt: "type", answer: "x", explanation: "e" }],
    { checkAnswers: {}, checkResults: {} },
  );
  assert.match(html, /data-check="0"[^>]*data-choice="0"/);
  assert.match(html, /data-check-input="1"/);
  assert.match(html, /Check your understanding/);
});

test("checksHTML shows the explanation and marker once answered", () => {
  const html = checksHTML(
    [{ type: "fill", prompt: "type", answer: "x", explanation: "because x" }],
    { checkAnswers: { 0: "x" }, checkResults: { 0: { correct: true } } },
  );
  assert.match(html, /because x/);
  assert.match(html, /Correct/);
});

test("checksHTML renders nothing for no checks", () => {
  assert.equal(checksHTML([], {}), "");
  assert.equal(checksHTML(undefined, {}), "");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/checks.test.js`
Expected: FAIL — cannot find `../src/views/checks.js`.

- [ ] **Step 3: Write `frontend/src/views/checks.js`:**

```javascript
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

const norm = (s) => String(s).trim().toLowerCase();

export function gradeCheck(check, answer) {
  const correct =
    check.type === "mcq"
      ? Number(answer) === check.answer
      : norm(answer) === norm(check.answer);
  return { correct, explanation: check.explanation };
}

function item(check, i, state) {
  const result = state.checkResults && state.checkResults[i];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state.checkAnswers[i])) cls = "choice wrong";
        }
        return `<button class="${cls}" data-check="${i}" data-choice="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state.checkAnswers && state.checkAnswers[i] != null ? state.checkAnswers[i] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input data-check-input="${i}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="check-fill" data-check="${i}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}

export function checksHTML(checks, state) {
  if (!checks || !checks.length) return "";
  const items = checks.map((c, i) => item(c, i, state)).join("");
  return `<section class="checks"><div class="checks-title">Check your understanding</div>${items}</section>`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/checks.test.js`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/checks.js frontend/tests/checks.test.js
git commit -m "feat(frontend): concept-check grading + rendering (mcq + fill)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire checks into the lesson screen

**What / Why / Verify:** Show the checks after the solution is revealed, grade on answer, show feedback, and log `lesson_check`. *Verify (unit):* the lesson view includes the checks section when the solution is revealed (it embeds `checksHTML`); all frontend tests pass. *Verify (real app):* deferred to Task 4.

**Files:**
- Modify: `frontend/src/views/lesson.js`
- Modify: `frontend/src/app.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/views.test.js` (extend)

**Interfaces:**
- Consumes: `checksHTML`/`gradeCheck` (Task 2); the existing lesson screen + `log()` payload support.
- Produces: `lessonHTML` renders `checksHTML(lesson.checks, state)` once `state.solutionRevealed`; `app.js` grades + logs answers.

- [ ] **Step 1: Write the failing test** — append to `frontend/tests/views.test.js` (the inline `SAMPLE_LESSON` fixture needs a `checks` field for this test; add one in the test):

```javascript
test("lesson renders the checks section once the solution is revealed", () => {
  const withChecks = {
    ...SAMPLE_LESSON,
    checks: [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
  };
  const revealed = lessonHTML(withChecks, { answer: "x", hintVisible: false, solutionRevealed: true, checkAnswers: {}, checkResults: {} });
  assert.match(revealed, /Check your understanding/);
  assert.match(revealed, /data-check-input="0"/);

  const notYet = lessonHTML(withChecks, { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} });
  assert.doesNotMatch(notYet, /Check your understanding/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/views.test.js`
Expected: FAIL — the lesson view does not render checks.

- [ ] **Step 3: Render checks in `frontend/src/views/lesson.js`** — add the import at the top and render the section after the lesson `</section>` and before `<div class="nav">`:

Add import:
```javascript
import { checksHTML } from "./checks.js";
```
Change the markup between the card close and the nav from:
```javascript
    </section>
    <div class="nav">
```
to:
```javascript
    </section>
    ${state.solutionRevealed ? checksHTML(lesson.checks || [], state) : ""}
    <div class="nav">
```

- [ ] **Step 4: Wire answering into `frontend/src/app.js`.**

Add the import:
```javascript
import { checksHTML } from "./views/checks.js"; // (only if needed elsewhere)
import { gradeCheck } from "./views/checks.js";
```
(`gradeCheck` is the one used in app.js; `checksHTML` is used by lesson.js, not app.js — import only `gradeCheck`.)

Add `checkAnswers: {}` and `checkResults: {}` to **each** place a fresh `ui.lessonState` is created — there are three: in `startLesson`, in `advanceAfterLesson`, and in `startReviewSession`. Each currently sets:
```javascript
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
```
change each to:
```javascript
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
```

In `paintLesson`, after the existing rating-button binding, add check wiring + the `answerCheck` helper:
```javascript
    view.querySelectorAll('[data-check-input]').forEach((inp) => {
      inp.addEventListener("input", () => {
        const i = Number(inp.getAttribute("data-check-input"));
        ui.lessonState.checkAnswers[i] = inp.value;
      });
    });
    view.querySelectorAll('[data-choice]').forEach((btn) => {
      btn.addEventListener("click", () =>
        answerCheck(Number(btn.getAttribute("data-check")), Number(btn.getAttribute("data-choice"))),
      );
    });
    view.querySelectorAll('[data-action="check-fill"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = Number(btn.getAttribute("data-check"));
        const inp = view.querySelector(`[data-check-input="${i}"]`);
        answerCheck(i, inp ? inp.value : "");
      });
    });
```

Add `answerCheck` (near `paintLesson`):
```javascript
  function answerCheck(i, answer) {
    const check = ui.lesson.checks && ui.lesson.checks[i];
    if (!check || ui.lessonState.checkResults[i]) return;
    const result = gradeCheck(check, answer);
    ui.lessonState.checkAnswers[i] = answer;
    ui.lessonState.checkResults[i] = { correct: result.correct };
    log("lesson_check", {
      courseId: ui.courseId,
      topicId: ui.lesson.id,
      payload: { index: i, type: check.type, correct: result.correct },
    });
    paintLesson();
  }
```

- [ ] **Step 5: Add check styles** — append to `frontend/styles.css`:

```css
/* =================  CONCEPT CHECKS  ================= */
.checks{display:flex; flex-direction:column; gap:14px; margin-top:4px}
.checks-title{font-size:13px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--text-mut)}
.check{display:flex; flex-direction:column; gap:8px}
.check-q{font-size:15px; color:var(--text); line-height:1.45}
.choice{text-align:left; padding:11px 14px; border:1px solid var(--border-field); border-radius:var(--r-sm);
  background:var(--glass-field); color:var(--text); font:14px/1.4 inherit; cursor:pointer; transition:all .15s}
.choice:hover:not(:disabled){background:rgba(255,255,255,.7)}
.choice.correct{border-color:#25b478; background:rgba(37,180,120,.14); color:#0f7a4f; font-weight:600}
.choice.wrong{border-color:#d06; background:rgba(208,0,102,.12); color:#a0064e}
.fill-row{display:flex; gap:8px}
.fill-row input{flex:1; padding:11px 14px; border:1px solid var(--border-field); border-radius:var(--r-sm);
  background:var(--glass-field); color:var(--text); font:14px/1.4 inherit}
.fill-answer{font-size:14px; color:var(--text-mut)}
.check-feedback{font-size:13px; line-height:1.5; padding:9px 12px; border-radius:var(--r-sm)}
.check-feedback.ok{background:rgba(37,180,120,.12); color:#0f7a4f}
.check-feedback.no{background:rgba(208,0,102,.10); color:#a0064e}
```

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && node --test`
Expected: PASS (all suites incl. the new checks + view tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/lesson.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js
git commit -m "feat(frontend): show + grade concept checks on the lesson screen; log lesson_check

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: End-to-end verification + deploy

**What / Why / Verify:** Prove checks generate + grade in a real browser, then ship. *Verify:* a generated lesson has checks; answering shows correct/incorrect + explanation; a `lesson_check` event lands.

**Files:** none changed (verification + deploy).

- [ ] **Step 1: Full local test sweep** — `.venv/bin/pytest -q` → PASS; `cd frontend && node --test` → PASS.

- [ ] **Step 2: Confirm the Pi's Claude login still works** (generation is needed for a real lesson):
```
mcp__pi-ssh__exec: env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN HOME=/home/werner PATH=/home/werner/.local/bin:$PATH timeout 60 claude -p 'Reply with ONLY {"ok": true}' --output-format json --model claude-sonnet-4-6
```
Expected: `is_error:false`. If it 401s, the Pi login expired — surface to Werner (re-auth needed) before the browser e2e.

- [ ] **Step 3: Deploy to the Pi**
```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then `mcp__pi-ssh__sudo-exec: systemctl restart claude-university` and confirm `systemctl is-active`.

- [ ] **Step 4: Real-browser check (Playwright, against `http://100.99.33.106:8200/`)**

1. Create a tiny course via the chat ("a 1-module, 1-lesson beginner course on the Python print function"); open it; Start session → wait for generation.
2. Confirm the lesson renders; reveal the solution → a **"Check your understanding"** section appears with one or more checks.
3. Answer an mcq wrong → it marks the choice wrong, highlights the correct one, shows the explanation. Answer a fill correctly → "Correct" + explanation.
4. Read events back: `mcp__pi-ssh__exec: curl -s 'http://localhost:8200/api/events?type=lesson_check'` → at least one event with `payload` `{index, type, correct}`.
5. Remove the throwaway course on the Pi and confirm the university is empty again.

- [ ] **Step 5: Confirm service active + enabled** — `systemctl is-active claude-university && systemctl is-enabled claude-university`.

---

## Self-Review

**1. Spec coverage:**
- Two check types (mcq + fill) → Task 1 (`valid_check`) + Task 2 (`gradeCheck`). ✓
- Checks in lesson JSON, generated + required → Task 1 (`lesson_prompt`, `valid_lesson`). ✓
- Sanitized check HTML → Task 1 (`ensure_lesson`). ✓
- Render after solution, grade with feedback → Tasks 2 (`checksHTML`) + 3 (lesson.js + app.js). ✓
- `lesson_check` events (`{index, type, correct}`) → Task 3 (`answerCheck`). ✓
- *Correctly deferred:* using results for mastery/adaptivity (Slice 6), player UX (Slice 7), extra check types.

**2. Placeholder scan:** No "TBD/TODO". Step 1b explicitly lists the four existing tests to update and the exact `_OK_CHECK` addition — concrete, not vague.

**3. Type consistency:** `valid_check(item)` and the `checks` item shapes (`{type, prompt, explanation, choices?, answer}`) are identical across `valid_lesson` (Task 1), `lesson_prompt` (Task 1), `gradeCheck`/`checksHTML` (Task 2), and the `answerCheck` wiring (Task 3). `answer` is an integer index for `mcq` (compared via `Number(answer) === check.answer`) and a string for `fill` (normalized compare) consistently. `state.checkAnswers`/`state.checkResults` produced by `app.js` (Task 3) are exactly what `checksHTML` (Task 2) consumes. `lesson_check` payload `{index, type, correct}` is produced in `answerCheck` and reuses the existing `log()`/events pipeline. `gradeCheck` is imported into `app.js`; `checksHTML` into `lesson.js`.
