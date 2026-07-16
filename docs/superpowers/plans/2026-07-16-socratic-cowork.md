# Socratic Co-work on the Exercise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional "Work through it with Claude" mode on the lesson exercise: the learner commits to steps in the side-chat and Claude guides with one Socratic question per turn, never revealing the answer.

**Architecture:** A mode flag on the existing lesson side-chat — no new route, screen, or store. The backend swaps the system prompt (`SOCRATIC_COWORK_SYSTEM` instead of `LESSON_CHAT_SYSTEM`) and drops web-search tools when the client sends `mode: "socratic"`; the frontend adds an entry button on the exercise card, a banner + Exit in the workspace chat tab, and an ephemeral `ws.socratic` flag that is never persisted.

**Tech Stack:** Flask backend (`backend/`), vanilla-JS frontend (`frontend/src/`, no build step, no frameworks), pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-07-16-socratic-cowork-design.md` — the single source of requirements. Implement exactly what it says, nothing extra.

## Ambiguity resolutions

Details the spec delegated to this plan, resolved by reading the real templates:

1. **Button placement:** in the exercise card (`frontend/src/views/lesson.js` `lessonHTML`), directly after `${gradeBlock(state)}` and before the hint toggle — grouped with the answer controls. Rendered only when `!state.solutionRevealed`. Uses the existing `btn-secondary` class plus the template's inline-margin idiom, so no new button CSS.
2. **Banner markup:** `<div class="ws-socratic"><span>…</span><button class="ws-socratic-exit" data-action="socratic-exit">Exit</button></div>`, rendered as the first child of `.ws-chat` (above `.ws-thread`). New CSS reuses the workspace purple-tint idiom (same colors as `.ws-tab.on`).
3. **Opener and banner strings:** the spec's strings verbatim (see Task 2/3 code).
4. **`SOCRATIC_COWORK_SYSTEM` text:** the spec's prompt text verbatim (no polish needed).
5. **`socratic-start` does not touch the `ws-prefs` localStorage record** — it force-opens the chat tab by mutating `ws.open`/`ws.tab` directly, exactly like the existing `explain-chat` handler (app.js:838-850).
6. **Re-entry after Exit pushes a fresh opener.** The entry guard (`!ws.socratic` before setting it) only prevents duplicates from repeated clicks while already in the mode, which is what the spec's "only on entry" requires.
7. **Backend test files live in `tests/` at the repo root** (`tests/test_generation.py`, `tests/test_courses_api.py`) — there is no `backend/tests/`.

## Global Constraints

Every task's requirements implicitly include this section.

- Backend tests: `.venv/bin/pytest -q` (from repo root). Frontend tests: `node --test frontend/tests/*.test.js` — the explicit glob is required; a bare directory silently runs nothing.
- After any `frontend/src/app.js` change, run the import-resolution check: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` (app.js is not unit-tested by repo convention).
- View logic that needs tests lives in `frontend/src/views/*.js` as pure exported helpers; `app.js` gets only wiring.
- Rendering safety: learner-typed or Claude-emitted text goes through `esc()` (`frontend/src/escape.js`) whenever injected via innerHTML; live streaming writes use `.textContent`. Never bypass either. (The opener and banner are static app-authored strings — no `esc()` needed on them.)
- Async wiring in app.js follows the capture-then-guard idiom: capture `ui.lessonState` (and any ids) before an `await`, re-check identity (the `sendWsChat` `onScreen()` pattern) before any DOM write after it. `ws.chat` mutation and `saveWorkspace` persistence are intentionally NOT gated — only DOM paints are. Preserve that.
- The workspace PUT body shape stays exactly `{notes, chat}` — `ws.socratic` must never be sent to or read from the server. `seedWorkspace` leaves the flag undefined on load (no change needed there).
- Backend guard idioms: `body = request.get_json(silent=True); body = body if isinstance(body, dict) else {}`; drop non-dict entries from lists before iterating. Match surrounding code style; comments only for non-obvious constraints.
- No emojis anywhere. No refactors or renames outside what this plan specifies.
- One commit per task. Message style `feat(socratic): <what>` / `test(socratic): <what>`, each commit message ending with the line:
  `Co-Authored-By: Claude <noreply@anthropic.com>`
- Do not persist the mode, log any new event, or touch mastery — formative only, per the spec.

---

### Task 1: Backend — socratic mode on the lesson chat route

**Files:**
- Modify: `backend/generation.py` (constant after `LESSON_CHAT_SYSTEM` which ends at line 828; `lesson_chat_prompt` at 831-847; `lesson_chat_sse` at 850-861)
- Modify: `backend/app.py` (`post_lesson_chat`, lines 513-527)
- Test: `tests/test_generation.py` (append after `test_lesson_chat_prompt_carries_solution_reveal_state`, which ends at line 856, before the `# ---- self-consistency ...` comment)
- Test: `tests/test_courses_api.py` (append after `test_lesson_chat_route_passes_solution_revealed`, which ends at line 491, before the `/revise` section comment)

**Interfaces:**
- Consumes: `claude_client.stream(prompt, *, model=DEFAULT_MODEL, spawn=_spawn_cli, tools=None)` (backend/claude_client.py:196); `_sse(event, data)` and `LESSON_CHAT_SYSTEM` already in generation.py; `_events(sse_chunks)` helper at tests/test_generation.py:162; `_fixture_course(courses, root)` helper at tests/test_courses_api.py:45; `client` fixture from tests/conftest.py.
- Produces: `generation.SOCRATIC_COWORK_SYSTEM` (str constant); `generation.lesson_chat_prompt(lesson, messages, solution_revealed=False, socratic=False)`; `generation.lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False, socratic=False)`; route accepts optional `"mode": "socratic"` in the POST body of `/api/courses/<course_id>/lessons/<lesson_id>/chat`. Task 3 relies on the route contract: body `{messages, solutionRevealed, mode?}`.

- [ ] **Step 1: Write the failing generation tests**

Append to `tests/test_generation.py`, directly after `test_lesson_chat_prompt_carries_solution_reveal_state` (ends line 856) and before the `# ---- self-consistency: prompt hardening + verification pass ----` comment:

```python
def test_socratic_cowork_system_rules():
    s = gen.SOCRATIC_COWORK_SYSTEM
    assert "NEVER state it" in s
    assert "Reveal solution button" in s
    assert "One question per turn" in s
    assert "under 80 words" in s
    assert "exercise answer box" in s


def test_lesson_chat_prompt_socratic_swaps_system_keeps_context():
    lesson = {"topic": "HTTP requests", "promptHtml": "<p>what is a GET</p>",
              "solutionAns": "GET /x", "solutionNote": "method+path"}
    p = gen.lesson_chat_prompt(lesson, [{"role": "user", "content": "first step?"}],
                               socratic=True)
    assert "NEVER state it" in p                      # socratic system present
    assert "ONE short guiding question" not in p      # default system replaced
    assert "HTTP requests" in p
    assert "what is a GET" in p
    assert "GET /x" in p                              # reference answer still in context
    assert "has NOT yet revealed the solution" in p
    assert "Learner: first step?" in p
    assert p.rstrip().endswith("You:")


def test_lesson_chat_prompt_socratic_carries_reveal_state():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    shown = gen.lesson_chat_prompt(lesson, [], solution_revealed=True, socratic=True)
    assert "has already revealed the solution" in shown


def test_lesson_chat_prompt_default_unchanged_without_socratic():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    p = gen.lesson_chat_prompt(lesson, [])
    assert "ONE short guiding question" in p
    assert "give it plainly" in p
    assert "NEVER state it" not in p


def test_lesson_chat_sse_threads_socratic_flag():
    seen = []

    def fake_stream(prompt):
        seen.append(prompt)
        yield "ok"

    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    chunks = list(gen.lesson_chat_sse(lesson, [], stream_fn=fake_stream, socratic=True))
    assert "NEVER state it" in seen[0]
    assert _events(chunks)[-1][0] == "done"
```

- [ ] **Step 2: Run the generation tests to verify they fail**

Run: `.venv/bin/pytest tests/test_generation.py -q -k socratic`
Expected: 5 failures — `AttributeError: module 'backend.generation' has no attribute 'SOCRATIC_COWORK_SYSTEM'` and `TypeError: lesson_chat_prompt() got an unexpected keyword argument 'socratic'` (the `default_unchanged` test may already pass; that is fine).

- [ ] **Step 3: Write the failing route tests**

Append to `tests/test_courses_api.py`, directly after `test_lesson_chat_route_passes_solution_revealed` (ends line 491) and before the `# /revise and /apply-revision` section comment:

```python
def test_lesson_chat_socratic_mode_swaps_prompt_and_drops_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "step 1?"}],
                             "mode": "socratic"})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)  # drain the lazy SSE generator
    assert "event: done" in text
    prompt, kw = calls[0]
    assert "NEVER state it" in prompt          # socratic system prompt selected
    assert not kw.get("tools")                 # WebSearch/WebFetch dropped


def test_lesson_chat_normal_mode_keeps_web_tools(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake_stream(prompt, **kw):
        calls.append((prompt, kw))
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    resp.get_data(as_text=True)
    assert calls[0][1].get("tools") == ["WebSearch", "WebFetch"]


def test_lesson_chat_mode_falls_back_to_normal_unless_socratic(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    prompts = []

    def fake_stream(prompt, **kw):
        prompts.append(prompt)
        return iter(["ok"])

    monkeypatch.setattr(claude_client, "stream", fake_stream)
    for mode in (None, "chat", 5, True):
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        if mode is not None:
            payload["mode"] = mode
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat", json=payload)
        assert resp.status_code == 200
        resp.get_data(as_text=True)
    assert len(prompts) == 4
    for p in prompts:
        assert "give it plainly" in p          # default system prompt
        assert "NEVER state it" not in p


def test_lesson_chat_forged_bodies_stream_without_500(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "stream", lambda prompt, **kw: iter(["ok"]))
    for payload in ([1, 2], "str", 5, {"messages": "x"}, {"messages": [1, {}]}):
        resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat", json=payload)
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert "event: done" in text
```

- [ ] **Step 4: Run the route tests to verify they fail**

Run: `.venv/bin/pytest tests/test_courses_api.py -q -k "socratic or forged or web_tools or falls_back"`
Expected: FAIL — the socratic test asserts `"NEVER state it" in prompt` (AssertionError), and the forged-body test raises `AttributeError: 'list' object has no attribute 'get'` from inside the route (exceptions propagate because the test app sets `TESTING=True`). `test_lesson_chat_normal_mode_keeps_web_tools` may already pass.

- [ ] **Step 5: Implement the generation.py changes**

In `backend/generation.py`, insert the new constant between the closing paren of `LESSON_CHAT_SYSTEM` (line 828) and `def lesson_chat_prompt` (line 831):

```python
# Socratic co-work: the committed never-reveals alternative to the side-chat's
# give-in-when-asked-twice behavior. The Reveal solution button is the escape hatch.
SOCRATIC_COWORK_SYSTEM = (
    "You are working through the lesson's MAIN EXERCISE with a learner who wants to reach "
    "the solution themselves. You have the reference answer below — NEVER state it, never "
    "lay out the full approach, and never confirm a bare guess as correct until the "
    "learner has explained the reasoning behind it. If they ask you directly for the "
    "answer or say they give up, warmly decline in one sentence, remind them the Reveal "
    "solution button is there if they want out, then offer a smaller step by breaking the "
    "current question into an easier one. Otherwise respond to the learner's LATEST step "
    "only: if it is right, confirm it in a few words and ask the ONE question that moves "
    "them a single step forward; if it is wrong or rests on a misconception, do not "
    "correct it outright — ask a short question or give a tiny concrete example that lets "
    "them see the problem themselves. One question per turn. Keep every turn under 80 "
    "words. Mirror the lesson's OWN vocabulary: use the exact terms, labels, and step "
    "names that appear in the lesson text below. When the learner has stated the complete "
    "solution in their own words, tell them plainly they have it and to type their final "
    "answer into the exercise answer box to check it."
)
```

Then replace `lesson_chat_prompt` (currently lines 831-847) with this complete final version — the only changes are the `socratic` kwarg and the `system` selection line; the context block, revealed line, and history rendering are byte-identical to today:

```python
def lesson_chat_prompt(lesson, messages, solution_revealed=False, socratic=False):
    revealed_line = ("The learner has already revealed the solution."
                     if solution_revealed
                     else "The learner has NOT yet revealed the solution.")
    ctx = (
        f"Lesson topic: {lesson.get('topic', '')}\n"
        f"Lesson prompt (HTML): {lesson.get('promptHtml', '')}\n"
        f"Reference answer: {lesson.get('solutionAns', '')}\n"
        f"Why it is right: {lesson.get('solutionNote', '')}\n"
    )
    system = SOCRATIC_COWORK_SYSTEM if socratic else LESSON_CHAT_SYSTEM
    lines = [system, "", "The lesson the learner is studying:", ctx,
             revealed_line, ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)
```

Then replace `lesson_chat_sse` (currently lines 850-861) with this complete final version — only the signature and the `lesson_chat_prompt` call change; error handling is untouched:

```python
def lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False, socratic=False):
    prompt = lesson_chat_prompt(lesson, messages, solution_revealed=solution_revealed,
                                socratic=socratic)
    try:
        for chunk in stream_fn(prompt):
            yield _sse("delta", chunk)
    except claude_client.ClaudeAuthError:
        yield _sse("error", json.dumps({"message": "Claude needs re-authentication on the Pi — run `claude` there to log in again."}))
        return
    except claude_client.ClaudeError:
        yield _sse("error", json.dumps({"message": "Claude is unavailable right now."}))
        return
    yield _sse("done", "{}")
```

- [ ] **Step 6: Implement the app.py route changes**

In `backend/app.py`, replace the whole `post_lesson_chat` function (currently lines 513-527) with:

```python
    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/chat")
    def post_lesson_chat(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            messages = []
        messages = [m for m in messages if isinstance(m, dict)]
        # Any forged mode value falls back to the normal chat: the flag only selects
        # between two system prompts (the reference answer is in context either way).
        socratic = body.get("mode") == "socratic"
        if socratic:
            # No web tools: the exercise is self-contained with the solution in
            # context, and toolless turns are faster.
            stream_fn = lambda p: claude_client.stream(p)
        else:
            # The side-chat can web-search so it isn't limited to the model's training cutoff;
            # the model only searches when the question needs current/factual info.
            stream_fn = lambda p: claude_client.stream(p, tools=["WebSearch", "WebFetch"])
        sse = generation.lesson_chat_sse(
            lesson, messages, stream_fn=stream_fn,
            solution_revealed=bool(body.get("solutionRevealed")), socratic=socratic)
        return app.response_class(sse, mimetype="text/event-stream")
```

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS (the new 9 plus every pre-existing test — the existing `test_lesson_chat_*` tests must still pass unchanged, proving `socratic=False` behavior is byte-identical).

- [ ] **Step 8: Commit**

```bash
git add tests/test_generation.py tests/test_courses_api.py backend/generation.py backend/app.py
git commit -m "feat(socratic): add socratic co-work mode to the lesson chat backend" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Frontend views — entry button and workspace mode banner

**Files:**
- Modify: `frontend/src/views/lesson.js` (`wsChatHTML` at 98-108; the exercise card template inside `lessonHTML`, around line 209)
- Modify: `frontend/styles.css` (append to the `/* lesson workspace — notes + side-chat panel */` block, after `.ws-send:disabled` at line 509)
- Test: `frontend/tests/views.test.js` (append after the `"open workspace chat tab escapes message content"` test, which ends at line 207)

**Interfaces:**
- Consumes: `lessonHTML(lesson, state, nav)` and its `state.ws` shape (`{open, tab, notes, chat, pending, saveStatus}`); `SAMPLE_LESSON` fixture at views.test.js:19.
- Produces: exercise card renders `<button class="btn-secondary" data-action="socratic-start">Work through it with Claude</button>` only when `!state.solutionRevealed`; `wsChatHTML` renders a `.ws-socratic` banner with a `data-action="socratic-exit"` button when `w.socratic` is truthy. Task 3 binds both `data-action` values and sets/clears `ws.socratic`.

- [ ] **Step 1: Write the failing view tests**

Append to `frontend/tests/views.test.js`, directly after the `"open workspace chat tab escapes message content"` test (ends line 207):

```js
test("exercise shows the socratic start button only before the solution is revealed", () => {
  const before = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(before, /data-action="socratic-start"/);
  assert.match(before, /Work through it with Claude/);
  const after = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.doesNotMatch(after, /data-action="socratic-start"/);
});

test("workspace chat shows the socratic banner and Exit only when the mode is on", () => {
  const base = { answer: "", hintVisible: false, solutionRevealed: false };
  const wsOn = { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "", socratic: true };
  const on = lessonHTML(SAMPLE_LESSON, { ...base, ws: wsOn });
  assert.match(on, /Working through the exercise — Claude will guide with questions, not answers\./);
  assert.match(on, /data-action="socratic-exit"/);
  assert.ok(on.indexOf("ws-socratic") < on.indexOf("ws-thread")); // banner sits above the thread
  const off = lessonHTML(SAMPLE_LESSON, { ...base, ws: { ...wsOn, socratic: false } });
  assert.doesNotMatch(off, /ws-socratic/);
  assert.doesNotMatch(off, /data-action="socratic-exit"/);
  // A falsy flag renders byte-identically to a workspace that has never seen the mode.
  const legacy = lessonHTML(SAMPLE_LESSON, { ...base, ws: { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "" } });
  assert.equal(off, legacy);
});
```

- [ ] **Step 2: Run the view tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the 2 new tests FAIL (`socratic-start` and the banner do not render yet); all others pass.

- [ ] **Step 3: Add the entry button to the exercise card**

In `frontend/src/views/lesson.js`, inside `lessonHTML`, change these two adjacent template lines (currently lines 208-210):

```js
      <button class="check-answer" data-action="check-answer"${state.answer.trim() && !state.grading ? "" : " disabled"}>${state.grade && !state.grade.error ? "Check again" : "Check my answer"}</button>
      ${gradeBlock(state)}
      <button class="hint-toggle" data-action="toggle-hint" style="margin:10px 0">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
```

to:

```js
      <button class="check-answer" data-action="check-answer"${state.answer.trim() && !state.grading ? "" : " disabled"}>${state.grade && !state.grade.error ? "Check again" : "Check my answer"}</button>
      ${gradeBlock(state)}
      ${state.solutionRevealed ? "" : `<button class="btn-secondary" data-action="socratic-start" style="margin:10px 0 0">Work through it with Claude</button>`}
      <button class="hint-toggle" data-action="toggle-hint" style="margin:10px 0">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
```

- [ ] **Step 4: Add the mode banner to the chat tab**

In `frontend/src/views/lesson.js`, replace the whole `wsChatHTML` function (currently lines 98-108) with:

```js
function wsChatHTML(w) {
  const banner = w.socratic
    ? `<div class="ws-socratic"><span>Working through the exercise — Claude will guide with questions, not answers.</span>` +
      `<button class="ws-socratic-exit" data-action="socratic-exit">Exit</button></div>`
    : "";
  const thread = (w.chat || [])
    .map((m) => `<div class="ws-msg ws-${m.role === "user" ? "you" : "ai"}">${esc(m.content)}</div>`)
    .join("");
  const pending = w.pending ? `<div class="ws-msg ws-ai ws-typing">…</div>` : "";
  return (
    `<div class="ws-chat">${banner}<div class="ws-thread">${thread}${pending}</div>` +
    `<div class="ws-compose"><textarea data-field="ws-chat" placeholder="Ask a side question…"${w.pending ? " disabled" : ""}></textarea>` +
    `<button class="ws-send" data-action="ws-send"${w.pending ? " disabled" : ""}>Send</button></div></div>`
  );
}
```

(The banner strings are static app-authored text — no `esc()` needed. When `w.socratic` is falsy, `banner` is `""` and the output is byte-identical to today.)

- [ ] **Step 5: Add the banner CSS**

In `frontend/styles.css`, append inside the workspace block, directly after the `.ws-send:disabled{opacity:.5; cursor:default}` line (509):

```css
.ws-socratic{display:flex; align-items:center; gap:10px; padding:9px 12px; border-radius:var(--r-sm);
  border:1px solid rgba(124,106,255,.3); background:rgba(124,106,255,.14); color:var(--purple); font-size:12px; line-height:1.4}
.ws-socratic span{flex:1}
.ws-socratic-exit{padding:5px 10px; border:1px solid rgba(124,106,255,.3); border-radius:var(--r-sm);
  background:none; color:var(--purple); font:600 12px/1 inherit; cursor:pointer}
.ws-socratic-exit:hover{background:rgba(124,106,255,.1)}
```

- [ ] **Step 6: Run the frontend tests to verify they pass**

Run: `node --test frontend/tests/*.test.js`
Expected: all tests PASS, including the 2 new ones and the pre-existing workspace tests (proving non-socratic markup is unchanged).

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/views.test.js frontend/src/views/lesson.js frontend/styles.css
git commit -m "feat(socratic): exercise entry button and workspace mode banner" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: app.js wiring — enter, exit, send flag, reveal clears the mode

**Files:**
- Modify: `frontend/src/app.js` only (`app.js` is not unit-tested by repo convention — wiring only):
  - opener constant next to `const WS_PREFS = "ws-prefs";` (line 686)
  - `sendWsChat` `extra` line (line 737)
  - `reveal-solution` handler (lines 790-796)
  - `socratic-start` binding in `paintLesson`, after the `explain-chat` block (ends line 850)
  - `socratic-exit` binding in `bindWorkspace`, before `scrollWsThread()` (line 942)

**Interfaces:**
- Consumes: `data-action="socratic-start"` / `data-action="socratic-exit"` markup from Task 2; the `mode: "socratic"` route contract from Task 1; existing in-scope identifiers `ui`, `view`, `root`, `fetch`, `storage`, `paintLesson`, `saveWorkspace` (all already used by the neighboring `explain-chat` handler and `sendWsChat`).
- Produces: ephemeral `ui.lessonState.ws.socratic` boolean (never persisted, dropped on reload; `seedWorkspace` is untouched and leaves it undefined).

- [ ] **Step 1: Add the opener constant**

In `frontend/src/app.js`, change (currently lines 685-686):

```js
  // ---- lesson workspace (notes + side-chat) ----
  const WS_PREFS = "ws-prefs"; // remembers open/closed + active tab across lessons
```

to:

```js
  // ---- lesson workspace (notes + side-chat) ----
  const WS_PREFS = "ws-prefs"; // remembers open/closed + active tab across lessons
  // Client-side canned opener for socratic co-work: instant, zero cost.
  const SOCRATIC_OPENER = "Let's work through this together — I'll ask questions, you do the thinking. What do you think the first step is?";
```

- [ ] **Step 2: Add the socratic-start handler in paintLesson**

In `frontend/src/app.js`, the `explain-chat` block inside `paintLesson` currently ends (lines 849-851):

```js
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
```

Insert the new handler between that block's closing `});` and the `back` line, so the region becomes:

```js
      paintLesson();
    });
    const socBtn = view.querySelector('[data-action="socratic-start"]');
    if (socBtn) socBtn.addEventListener("click", () => {
      const ws = ui.lessonState.ws;
      if (!ws) return; // workspace still seeding; the button works once it has painted
      const entering = !ws.socratic;
      ws.socratic = true;
      ws.open = true;
      ws.tab = "chat";
      if (entering) {
        ws.chat.push({ role: "assistant", content: SOCRATIC_OPENER });
        // Best-effort persist — same fire-and-forget idiom as the explain-chat seeding.
        saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
      }
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
```

(The `entering` guard means repeated clicks while the mode is active do not duplicate the opener; like `explain-chat`, this handler does not call `setWsPrefs` — the forced open/chat state is per-lesson-view, not a saved preference. No `await` in this handler, so no stale-screen guard is needed.)

- [ ] **Step 3: Add the socratic-exit handler in bindWorkspace**

In `frontend/src/app.js`, `bindWorkspace` currently ends (lines 940-943):

```js
    const wsSend = view.querySelector('[data-action="ws-send"]');
    if (wsSend) wsSend.addEventListener("click", sendWsChat);
    scrollWsThread();  // open/repaint with the newest message in view
  }
```

Change it to:

```js
    const wsSend = view.querySelector('[data-action="ws-send"]');
    if (wsSend) wsSend.addEventListener("click", sendWsChat);
    const socExit = view.querySelector('[data-action="socratic-exit"]');
    if (socExit) socExit.addEventListener("click", () => {
      ui.lessonState.ws.socratic = false;
      paintLesson();
    });
    scrollWsThread();  // open/repaint with the newest message in view
  }
```

- [ ] **Step 4: Clear the mode when the solution is revealed**

In `frontend/src/app.js`, replace the `reveal-solution` handler (currently lines 790-796):

```js
    view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
      if (!ui.lessonState.answer.trim()) return;
      if (!ui.lessonState.solutionRevealed)
        log("solution_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      ui.lessonState.solutionRevealed = true;
      paintLesson();
    });
```

with:

```js
    view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
      if (!ui.lessonState.answer.trim()) return;
      if (!ui.lessonState.solutionRevealed)
        log("solution_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      ui.lessonState.solutionRevealed = true;
      if (ui.lessonState.ws) ui.lessonState.ws.socratic = false; // mode ends on reveal
      paintLesson();
    });
```

- [ ] **Step 5: Send the mode flag from sendWsChat**

In `frontend/src/app.js`, inside `sendWsChat`, change the `extra` line (currently line 737):

```js
      extra: { solutionRevealed: !!ui.lessonState.solutionRevealed },
```

to:

```js
      extra: { solutionRevealed: !!ui.lessonState.solutionRevealed, ...(ws.socratic ? { mode: "socratic" } : {}) },
```

(`ws` here is the already-captured `ls.ws` from the top of `sendWsChat` — the mode flag is read from the captured state, per the existing capture-then-guard idiom. Do not change anything else in `sendWsChat`: the `onScreen()` DOM gating, and the intentionally ungated `ws.chat` mutation and `saveWorkspace` persistence, stay exactly as they are.)

- [ ] **Step 6: Run the import-resolution check**

Run (from repo root): `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected output: `imports ok`

- [ ] **Step 7: Run both test suites as a regression check**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS.
Run: `.venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app.js
git commit -m "feat(socratic): wire mode entry, exit, send flag, and reveal clearing in app.js" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-review (spec coverage check)

Ran against `docs/superpowers/specs/2026-07-16-socratic-cowork-design.md`:

- `SOCRATIC_COWORK_SYSTEM` verbatim, next to `LESSON_CHAT_SYSTEM` — Task 1 Step 5.
- `lesson_chat_prompt` / `lesson_chat_sse` thread a `socratic` kwarg, single builder, no duplication — Task 1 Step 5.
- Route: forged-body guard, messages shape guard (non-list -> `[]`, non-dict entries dropped), `mode == "socratic"` parsing with fallback, socratic drops WebSearch/WebFetch, normal keeps them — Task 1 Step 6; all four spec'd backend test groups — Task 1 Steps 1 and 3.
- Button gated on `!state.solutionRevealed`; banner + Exit gated on `ws.socratic`; non-socratic markup byte-identical (asserted with `assert.equal`) — Task 2.
- `socratic-start` (opener pushed only on entry, best-effort save, opens Chat tab), `socratic-exit`, reveal clears the mode, `sendWsChat` sends `mode: "socratic"` from the captured state, `{notes, chat}` PUT shape untouched, `seedWorkspace` untouched — Task 3.
- Formative only: no events, no mastery, no persistence of the flag — no task touches events.py, mastery.py, notes.py, or eventlog.js.
- Out of scope items (turn caps, mode persistence, other Claude-in-lessons items) — not implemented anywhere in this plan.

No placeholders; names and signatures are consistent across tasks (`SOCRATIC_COWORK_SYSTEM`, `socratic=`, `mode: "socratic"`, `data-action="socratic-start"` / `"socratic-exit"`, `ws.socratic`, `SOCRATIC_OPENER`). No spec contradictions found.
