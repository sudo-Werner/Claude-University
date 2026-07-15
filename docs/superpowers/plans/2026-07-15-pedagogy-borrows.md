# Pedagogy Borrows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guided-first help on the lesson exercise in the side-chat (with a friction-free direct-answer path), and a metacognitive follow-up question after explain-it-back grading that can be explored in the side-chat.

**Architecture:** Backend: prompt/validator changes in `generation.py` plus two one-line route touches in `app.py` (chat gains a `solutionRevealed` passthrough; explain switches to a stricter validator). Frontend: `streamChat` gains an `extra` body param; the explain card renders the follow-up + a seed-to-chat button; app.js wires the seed handler.

**Tech Stack:** existing Flask + ES modules; no new endpoints, no schema changes.

**Spec:** `docs/superpowers/specs/2026-07-15-pedagogy-borrows-design.md`

## Global Constraints

- Backend tests: `.venv/bin/pytest` from repo root. Frontend tests: `node --test frontend/tests/*.test.js` (glob, never a bare directory). After touching app.js: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`.
- Commit per task on branch `feat/pedagogy-borrows`. Never merge or push. No emojis.
- Server-sanitization boundary: `followUp` is sanitized server-side with `sanitize_html` exactly like `note`, and rendered RAW client-side (client `esc()` would double-escape). Learner-typed text stays `esc()`'d.
- `/grade` and its `valid_grade` behavior are untouched; only `/explain` switches to `valid_explain`.
- The intake chat (`/api/courses/chat`, `build_chat_prompt`, `COURSE_SYSTEM_PROMPT`) is untouched.

---

### Task 1: Backend — guided-first chat + explain followUp

**Files:**
- Modify: `backend/generation.py` (`LESSON_CHAT_SYSTEM`, `lesson_chat_prompt`, `lesson_chat_sse`, `valid_explain` new, `explain_prompt`, `explain_answer`)
- Modify: `backend/app.py` (lesson chat route: `solutionRevealed` passthrough; explain route: `valid_explain`)
- Modify: `tests/test_generation.py`, `tests/test_courses_api.py`

**Interfaces:**
- Produces: `lesson_chat_prompt(lesson, messages, solution_revealed=False)`; `lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False)`; `valid_explain(obj)`; `/explain` response gains required `followUp` (sanitized). Task 2 consumes `followUp` from the explain response and sends `solutionRevealed` in the chat POST body.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generation.py`:

```python
def test_lesson_chat_system_guides_first_with_escape_hatch():
    s = generation.LESSON_CHAT_SYSTEM
    assert "MAIN EXERCISE" in s
    assert "ONE short guiding question" in s
    assert "give it plainly" in s


def test_lesson_chat_prompt_carries_solution_reveal_state():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    hidden = generation.lesson_chat_prompt(lesson, [])
    assert "has NOT yet revealed the solution" in hidden
    shown = generation.lesson_chat_prompt(lesson, [], solution_revealed=True)
    assert "has already revealed the solution" in shown
    assert "has NOT yet revealed" not in shown


def test_valid_explain_requires_followup():
    base = {"verdict": "close", "note": "good try"}
    assert not generation.valid_explain(base)
    assert not generation.valid_explain({**base, "followUp": "  "})
    assert generation.valid_explain({**base, "followUp": "Why does that hold?"})
    assert not generation.valid_explain({**base, "verdict": "nope", "followUp": "q"})


def test_explain_prompt_asks_for_followup():
    p = generation.explain_prompt(prompt_html="<p>q</p>", solution_ans="a",
                                  solution_note="n", explanation="e")
    assert "followUp" in p
    assert "weakest point" in p
    assert "transfer question" in p


def test_explain_answer_sanitizes_followup(tmp_path):
    # extend the existing explain_answer test pattern: the mocked generate returns
    # {"verdict": "close", "note": "<script>x</script>ok", "followUp": "<script>y</script>why?"}
    # assert the returned followUp has the script escaped and the verdict/note behavior unchanged
    ...
```

(The last test adapts the file's existing `explain_answer` test fixtures — copy their course/lesson setup; assert `"<script>" not in out["followUp"]` and `"why?" in out["followUp"]`.)

In `tests/test_courses_api.py`: the existing explain-route tests mock the grade payload — add `"followUp": "Why?"` to those mocked returns (the route now validates with `valid_explain`, so a followUp-less mock would 502) and assert the response JSON includes `followUp`. Add one test that POSTs to the lesson chat route with `{"messages": [...], "solutionRevealed": true}` and asserts 200 (passthrough smoke test; the prompt-level behavior is covered in test_generation).

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -q`
Expected: new tests FAIL (missing phrases, `valid_explain` absent); existing explain route tests fail only after the route switch in Step 3 — add the `followUp` field to their mocks in this step so they keep passing.

- [ ] **Step 3: Implement**

(a) Append to `LESSON_CHAT_SYSTEM` (inside the existing parenthesized string, after the web-search sentence):

```python
    " When the learner asks for help with the lesson's MAIN EXERCISE and the solution is "
    "not yet revealed, do not hand over the full approach: respond first with ONE short "
    "guiding question or a targeted hint that moves them a single step forward. The moment "
    "they explicitly ask for the direct answer, say they are stuck, or ask a second time, "
    "give it plainly — no gatekeeping, no lecture about how they should learn. Questions "
    "about concepts, background, or tangents get a direct concise answer as always; once "
    "the solution is revealed, discuss it directly."
```

(b) `lesson_chat_prompt` — new signature and one added context line:

```python
def lesson_chat_prompt(lesson, messages, solution_revealed=False):
    revealed_line = ("The learner has already revealed the solution."
                     if solution_revealed
                     else "The learner has NOT yet revealed the solution.")
    ctx = (
        f"Lesson topic: {lesson.get('topic', '')}\n"
        f"Lesson prompt (HTML): {lesson.get('promptHtml', '')}\n"
        f"Reference answer: {lesson.get('solutionAns', '')}\n"
        f"Why it is right: {lesson.get('solutionNote', '')}\n"
    )
    lines = [LESSON_CHAT_SYSTEM, "", "The lesson the learner is studying:", ctx,
             revealed_line, ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)
```

(c) `lesson_chat_sse` gains the kwarg and passes it through:

```python
def lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False):
    prompt = lesson_chat_prompt(lesson, messages, solution_revealed=solution_revealed)
```
(rest of the function unchanged)

(d) `backend/app.py` lesson chat route — pass the flag:

```python
        sse = generation.lesson_chat_sse(
            lesson, body.get("messages", []), stream_fn=stream_fn,
            solution_revealed=bool(body.get("solutionRevealed")))
```

(e) `valid_explain` directly below `valid_grade`:

```python
def valid_explain(obj):
    if not valid_grade(obj):
        return False
    follow = obj.get("followUp")
    return isinstance(follow, str) and bool(follow.strip())
```

(f) `explain_prompt` — replace the final JSON-shape instruction with:

```python
        "Decide whether the explanation is correct, close (right idea, a gap or error), or "
        "incorrect. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"verdict":"correct"|"close"|"incorrect","note":"<one or two encouraging sentences '
        "addressed to 'you': what your explanation captured, then the single most important "
        'idea it missed or got wrong>","followUp":"<ONE short reflective question addressed '
        "to 'you' that targets the weakest point of the explanation and pushes you to justify "
        "or connect it; if the explanation was fully correct, ask a transfer question that "
        'connects the idea to a new situation instead>"}'
```

(g) `explain_answer` — return the sanitized followUp (validator is supplied by the route):

```python
    return {"verdict": result["verdict"], "note": sanitize_html(result["note"]),
            "followUp": sanitize_html(result["followUp"])}
```

(h) `backend/app.py` explain route — switch the validator:

```python
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_explain)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -q`
Expected: all PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS.

```bash
git add backend/generation.py backend/app.py tests/test_generation.py tests/test_courses_api.py
git commit -m "feat(chat+explain): guided-first exercise help; metacognitive followUp on explain"
```

---

### Task 2: Frontend — followUp card + seed side-chat, solutionRevealed passthrough

**Files:**
- Modify: `frontend/src/chat.js` (`streamChat` gains `extra`)
- Modify: `frontend/src/views/lesson.js` (`explainHTML` renders followUp + button)
- Modify: `frontend/src/app.js` (ws-send passes `extra`; new `explain-chat` handler)
- Modify: `frontend/styles.css` (one small rule)
- Test: `frontend/tests/` (extend the lesson-view and chat test files that already exist)

**Interfaces:**
- Consumes: explain response `{verdict, note, followUp}` (Task 1); `ui.lessonState.ws` = `{open, tab, notes, chat: [...], pending, saveStatus}`; `saveWorkspace({fetch, storage, courseId, lessonId, notes, chat})` (both already exist in app.js).
- Produces: `streamChat({..., extra = {}})` merging `extra` into the POST body.

- [ ] **Step 1: Write the failing tests**

In the frontend test file that covers `streamChat` (or a new `frontend/tests/chat-extra.test.js` following the existing chat test's fake-fetch pattern):

```js
test("streamChat merges extra fields into the POST body", async () => {
  let sent;
  const fakeFetch = async (url, opts) => {
    sent = JSON.parse(opts.body);
    return { body: emptyStreamBody() }; // reuse/adapt the existing test helper for an SSE body
  };
  await streamChat({ fetch: fakeFetch, messages: [{ role: "user", content: "hi" }],
                     endpoint: "/x", extra: { solutionRevealed: true },
                     onDelta: () => {}, onDone: () => {} });
  assert.equal(sent.solutionRevealed, true);
  assert.equal(sent.messages.length, 1);
});
```

In the lesson-view test file, alongside the existing explain-card tests:

```js
test("explain card renders followUp question and seed button after grading", () => {
  const html = lessonHTML(lessonFixture(), stateWith({
    solutionRevealed: true,
    explain: { text: "my take", grade: { verdict: "close", note: "n", followUp: "Why <em>exactly</em>?" } },
  }));
  assert.ok(html.includes("Why <em>exactly</em>?"));          // server-sanitized, rendered raw
  assert.ok(html.includes('data-action="explain-chat"'));
  assert.ok(html.includes("Explore in side-chat"));
});

test("explain seed button disables after seeding", () => {
  const html = lessonHTML(lessonFixture(), stateWith({
    solutionRevealed: true,
    explain: { seeded: true, grade: { verdict: "close", note: "n", followUp: "Q?" } },
  }));
  assert.ok(/data-action="explain-chat"[^>]*disabled/.test(html));
  assert.ok(html.includes("Sent to side-chat"));
});

test("explain card shows no seed button without followUp", () => {
  const html = lessonHTML(lessonFixture(), stateWith({
    solutionRevealed: true,
    explain: { grade: { verdict: "close", note: "n" } },
  }));
  assert.ok(!html.includes("explain-chat"));
});
```

(`lessonFixture()`/`stateWith()` stand for this test file's existing fixture conventions — reuse them.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the new tests FAIL; everything else passes.

- [ ] **Step 3: Implement**

(a) `frontend/src/chat.js` — signature and body:

```js
export async function streamChat({ fetch, messages, endpoint = "/api/courses/chat", extra = {}, onDelta, onBrief, onDone, onError }) {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, ...extra }),
  });
```
(rest unchanged)

(b) `frontend/src/app.js` — in the workspace ws-send handler's `streamChat({...})` call, add:

```js
      extra: { solutionRevealed: !!ui.lessonState.solutionRevealed },
```

(c) `frontend/src/views/lesson.js` — in `explainHTML`, inside the `else if (g)` branch, after building the grade `result` div, append:

```js
    if (g.followUp) {
      const seeded = !!ex.seeded;
      result +=
        `<div class="explain-followup"><div class="grade-note">${g.followUp}</div>` +
        `<button class="btn-secondary" data-action="explain-chat"${seeded ? " disabled" : ""}>` +
        `${seeded ? "Sent to side-chat" : "Explore in side-chat"}</button></div>`;
    }
```

(d) `frontend/src/app.js` — directly after the `exBtn` click handler block, add:

```js
    const exChat = view.querySelector('[data-action="explain-chat"]');
    if (exChat) exChat.addEventListener("click", () => {
      const ex = ui.lessonState.explain || {};
      const g = ex.grade;
      const ws = ui.lessonState.ws;
      if (!g || g.error || !g.followUp || ex.seeded || !ws) return;
      ex.seeded = true;
      ws.open = true;
      ws.tab = "chat";
      ws.chat.push({ role: "assistant", content: g.followUp });
      saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
      paintLesson();
    });
```

(match the exact `saveWorkspace` call signature already used elsewhere in app.js — copy it from the existing ws code.)

(e) `frontend/styles.css` — after the existing `.explain` rules:

```css
.explain-followup { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); }
.explain-followup .grade-note { margin-bottom: 8px; font-style: italic; }
```

- [ ] **Step 4: Run tests + import check**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS.
Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: `imports ok`.

- [ ] **Step 5: Full backend suite untouched check, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS (backend untouched by this task).

```bash
git add frontend/src/chat.js frontend/src/views/lesson.js frontend/src/app.js frontend/styles.css frontend/tests/
git commit -m "feat(lesson): explain followUp card seeds side-chat; chat carries solutionRevealed"
```
