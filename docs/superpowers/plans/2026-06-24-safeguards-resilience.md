# Content-Quality Safeguards & Resilience (Slice 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect Claude auth failures and surface a clear "re-authenticate on the Pi" message;
reject obviously-empty generated lessons (regenerate via the existing retry); allow `<hr>`; remove
the dropped streak placeholder.

**Architecture:** A `ClaudeAuthError` raised from the Claude CLI boundary keys on the CLI's
structured `api_error_status` (401/403) — verified against a real failed call — surfaced distinctly
by the lesson route, the chat stream, and the lesson screen. Stricter `valid_*` heuristics feed the
existing `run_structured` retry. No new LLM calls.

**Tech Stack:** Flask + SQLite (`.venv/bin/pytest`), plain ES modules (`node --test`).

## Global Constraints

- Auth detection on **success (exit 0)** must use ONLY the structured `api_error_status` field —
  never a text scan of stdout (a real lesson's content can contain words like "log in"/"401"). The
  text-marker fallback runs ONLY on a non-zero exit (where stdout is an error envelope, not lesson
  content) and on stderr.
- The real failure envelope (captured from the Pi): non-zero exit, stdout JSON with
  `"api_error_status":401` and `"result":"Invalid API key · Fix external API key"`.
- No extra LLM calls — the quality check is pure string logic; regeneration uses the existing
  `run_structured` single retry.
- `ClaudeAuthError` subclasses `ClaudeError` (so existing generic `except ClaudeError` still catches
  it where not specifically handled).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Auth-failure detection in the Claude client

**Files:**
- Modify: `backend/claude_client.py`
- Test: `tests/test_claude_client.py` (add cases)

**Interfaces:**
- Produces: `ClaudeAuthError(ClaudeError)`; `_auth_failure_reason(stdout, stderr, *, scan_text)
  -> str|None`. `_run_cli`/`_spawn_cli`/`stream` raise `ClaudeAuthError` on auth failure.

- [ ] **Step 1: Write failing tests** (append to `tests/test_claude_client.py`)

```python
def test_auth_failure_reason_detects_401_envelope():
    envelope = json.dumps({"is_error": True, "api_error_status": 401,
                           "result": "Invalid API key · Fix external API key"})
    assert "Invalid API key" in cc._auth_failure_reason(envelope, "", scan_text=True)
    # structured field is trusted even without text scan (success-path call):
    assert cc._auth_failure_reason(envelope, "", scan_text=False)


def test_auth_failure_reason_text_markers_only_when_scanning():
    err = "stuff: please run /login to authenticate"
    assert cc._auth_failure_reason("", err, scan_text=True)
    # a SUCCESS lesson whose content mentions auth words must NOT be flagged:
    lesson = json.dumps({"api_error_status": None,
                         "result": "Lesson: to log in, type your 401 code"})
    assert cc._auth_failure_reason(lesson, "", scan_text=False) is None


def test_run_cli_raises_auth_error_on_401(monkeypatch):
    class P:
        returncode = 1
        stdout = json.dumps({"api_error_status": 401, "result": "Invalid API key"})
        stderr = ""
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(cc.ClaudeAuthError):
        cc._run_cli(["-p", "x"])


def test_run_cli_plain_error_on_nonauth_failure(monkeypatch):
    class P:
        returncode = 2
        stdout = ""
        stderr = "some other crash"
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(cc.ClaudeError) as ei:
        cc._run_cli(["-p", "x"])
    assert not isinstance(ei.value, cc.ClaudeAuthError)


def test_run_cli_success_passthrough(monkeypatch):
    class P:
        returncode = 0
        stdout = json.dumps({"api_error_status": None, "result": "ok"})
        stderr = ""
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    assert cc._run_cli(["-p", "x"]) == P.stdout


def test_stream_raises_auth_error_on_401_line():
    line = json.dumps({"type": "result", "api_error_status": 401, "result": "Invalid API key"})
    with pytest.raises(cc.ClaudeAuthError):
        list(cc.stream("hi", spawn=lambda args: iter([line])))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_claude_client.py -q -k "auth or run_cli or stream_raises"`
Expected: FAIL (`ClaudeAuthError`/`_auth_failure_reason` undefined).

- [ ] **Step 3: Implement in `backend/claude_client.py`**

Add after `class ClaudeError`:

```python
class ClaudeAuthError(ClaudeError):
    """Claude CLI could not authenticate (expired/invalid Max login)."""


_AUTH_MARKERS = (
    "invalid api key", "unauthorized", " 401", "please run /login", "/login",
    "log in", "oauth", "authentication_error", "expired", "not logged in",
)


def _auth_failure_reason(stdout, stderr, *, scan_text):
    try:
        env = json.loads(stdout)
    except (ValueError, TypeError):
        env = None
    if isinstance(env, dict) and env.get("api_error_status") in (401, 403):
        return env.get("result") or ("Claude authentication failed (HTTP %s)." % env.get("api_error_status"))
    if scan_text:
        blob = ((stdout or "") + " " + (stderr or "")).lower()
        if any(m in blob for m in _AUTH_MARKERS):
            return "Claude authentication failed — the Pi login looks invalid."
    return None
```

Replace `_run_cli`:

```python
def _run_cli(args):
    proc = subprocess.run(
        [CLAUDE_BIN, *args], capture_output=True, text=True, env=_env(), timeout=_TIMEOUT
    )
    if proc.returncode != 0:
        reason = _auth_failure_reason(proc.stdout, proc.stderr, scan_text=True)
        if reason:
            raise ClaudeAuthError(reason)
        raise ClaudeError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
    reason = _auth_failure_reason(proc.stdout, "", scan_text=False)
    if reason:
        raise ClaudeAuthError(reason)
    return proc.stdout
```

In `_spawn_cli`, change the non-zero-exit branch to detect auth via stderr:

```python
    proc.wait()
    if proc.returncode != 0:
        err = (proc.stderr.read() or "")
        reason = _auth_failure_reason("", err, scan_text=True)
        if reason:
            raise ClaudeAuthError(reason)
        raise ClaudeError(f"claude stream exited {proc.returncode}: {err[:500]}")
```

In `stream`, detect a 401 envelope line (structured only) before extracting text:

```python
def stream(prompt, *, model=DEFAULT_MODEL, spawn=_spawn_cli):
    args = ["-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model]
    for line in spawn(args):
        try:
            ev = json.loads(line)
        except ValueError:
            ev = None
        if isinstance(ev, dict) and ev.get("api_error_status") in (401, 403):
            raise ClaudeAuthError(ev.get("result") or "Claude authentication failed.")
        text = _extract_stream_text(line)
        if text:
            yield text
```

- [ ] **Step 4: Run tests** — `.venv/bin/pytest tests/test_claude_client.py -q` then `.venv/bin/pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/claude_client.py tests/test_claude_client.py
git commit -m "feat(backend): detect Claude auth failures (401) as ClaudeAuthError"
```

---

### Task 2: Quality heuristic, `<hr>`, and auth surfacing (backend)

**Files:**
- Modify: `backend/generation.py` (`valid_check`, `valid_lesson`, `_ALLOWED_HTML`, `chat_sse`),
  `backend/app.py` (`get_lesson`)
- Test: `tests/test_generation.py`, `tests/test_courses_api.py` (add cases)

**Interfaces:**
- Consumes: `claude_client.ClaudeAuthError`.
- Produces: stricter `valid_check`/`valid_lesson`; `<hr>` in the sanitizer; `chat_sse` emits the
  re-auth message on `ClaudeAuthError`; lesson route returns `503 {code:"reauth"}` on it.

- [ ] **Step 1: Write failing tests**

In `tests/test_generation.py`:

```python
def test_valid_check_rejects_empty_fields():
    assert not gen.valid_check({"type": "mcq", "prompt": "  ", "choices": ["a", "b"], "answer": 0, "explanation": "e"})
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", ""], "answer": 0, "explanation": "e"})
    assert not gen.valid_check({"type": "fill", "prompt": "p", "answer": "  ", "explanation": "e"})
    assert gen.valid_check({"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"})


def test_valid_lesson_rejects_empty_prose():
    good = {k: "x" for k in gen.LESSON_KEYS}
    good["checks"] = [dict(_OK_CHECK)]
    assert gen.valid_lesson(good) is True
    blank = dict(good); blank["promptHtml"] = "   "
    assert gen.valid_lesson(blank) is False
    blank2 = dict(good); blank2["solutionAns"] = ""
    assert gen.valid_lesson(blank2) is False


def test_sanitize_html_allows_hr():
    out = gen.sanitize_html("<p>a</p><hr><p>b</p><hr/>")
    assert "<hr>" in out
    assert out.count("<hr>") == 2  # both <hr> and <hr/> normalize to <hr>


def test_chat_sse_emits_reauth_on_auth_error():
    def failing_stream(prompt):
        raise claude_client.ClaudeAuthError("Invalid API key")
        yield
    chunks = list(gen.chat_sse([{"role": "user", "content": "hi"}], {}, stream_fn=failing_stream))
    evs = _events(chunks)
    msg = [d for (e, d) in evs if e == "error"]
    assert msg and ("re-authenticate" in msg[0].lower() or "log in" in msg[0].lower())
```

In `tests/test_courses_api.py` (reuse the `_fixture_course` pattern, but here the lesson must NOT
exist on disk so generation runs; monkeypatch the generator to raise):

```python
def test_lesson_route_returns_reauth_on_auth_error(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, generation
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest = courses.write_course(root, {
        "title": "Auth Demo", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    # no lesson file on disk -> generation path; force an auth failure
    def boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("Invalid API key")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    resp = client.get(f"/api/courses/{cid}/lessons/{lid}")
    assert resp.status_code == 503
    assert resp.get_json().get("code") == "reauth"
```

- [ ] **Step 2: Run to verify they fail** — `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -q -k "empty or hr or reauth"` → FAIL.

- [ ] **Step 3: Implement**

In `backend/generation.py`, add `hr` void-tag entries to the static `_ALLOWED_HTML` dict (next to
the `br` entries):

```python
    "&lt;hr&gt;": "<hr>", "&lt;hr/&gt;": "<hr>", "&lt;hr /&gt;": "<hr>",
```

Tighten `valid_check` — add non-empty checks (keep the existing type/structure logic):

```python
def valid_check(item):
    if not isinstance(item, dict) or not isinstance(item.get("prompt"), str) \
            or not isinstance(item.get("explanation"), str):
        return False
    if not item["prompt"].strip() or not item["explanation"].strip():
        return False
    if item.get("type") == "mcq":
        choices = item.get("choices")
        answer = item.get("answer")
        return (isinstance(choices, list) and len(choices) >= 2
                and all(isinstance(c, str) and c.strip() for c in choices)
                and isinstance(answer, int) and 0 <= answer < len(choices))
    if item.get("type") == "fill":
        return isinstance(item.get("answer"), str) and bool(item["answer"].strip())
    return False
```

Tighten `valid_lesson` — require the prose fields non-empty (add before the `return`):

```python
def valid_lesson(obj):
    if not (isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)):
        return False
    for field in ("promptHtml", "hintHtml", "solutionAns", "solutionNote"):
        if not (isinstance(obj.get(field), str) and obj[field].strip()):
            return False
    checks = obj.get("checks")
    if not (isinstance(checks, list) and 1 <= len(checks) <= 3):
        return False
    return all(valid_check(c) for c in checks)
```

In `chat_sse`, handle the auth error distinctly (it is raised from `stream_fn`):

```python
def chat_sse(messages, profile, *, stream_fn):
    prompt = build_chat_prompt(messages, profile)
    full = []
    try:
        for chunk in stream_fn(prompt):
            full.append(chunk)
            yield _sse("delta", chunk)
    except claude_client.ClaudeAuthError:
        yield _sse("error", json.dumps({"message": "Claude needs re-authentication on the Pi — run `claude` there to log in again."}))
        return
    except claude_client.ClaudeError:
        yield _sse("error", json.dumps({"message": "Claude is unavailable right now."}))
        return
    proposal = detect_proposal("".join(full))
    if proposal is not None:
        yield _sse("proposal", json.dumps(proposal))
    yield _sse("done", "{}")
```

In `backend/app.py` `get_lesson`, catch the auth error BEFORE the generic `ClaudeError`:

```python
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this lesson"}), 502
```

(`ensure_lesson`'s `generate` callback calls `run_structured`, which propagates `ClaudeAuthError`
unretried since it is raised from the runner.)

- [ ] **Step 4: Run** — `.venv/bin/pytest -q`. Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py backend/app.py tests/test_generation.py tests/test_courses_api.py
git commit -m "feat(backend): reject empty lessons, allow <hr>, surface auth re-auth message"
```

---

### Task 3: Frontend — remove streak; surface lesson-load failure

**Files:**
- Modify: `frontend/src/views/shell.js`, `frontend/src/views/dashboard.js`, `frontend/src/app.js`,
  `frontend/src/courses.js`
- Test: `frontend/tests/views.test.js` (update streak assertions if any; add a no-streak assertion)

**Interfaces:**
- `shellHTML({ back })` (drop `streakDays`); `dashboardHTML(data, timerView)` no longer renders a
  streak strip (ignores `data.streakDays`). `loadLesson` returns `{error}` on failure.

- [ ] **Step 1: Read** `shell.js`, `dashboard.js` (the `.streak-strip` line), `app.js`
  (`STREAK_DAYS` + every `shellHTML(... streakDays ...)` / `sessionData` `streakDays`), and the
  current `views.test.js` for any streak assertions.

- [ ] **Step 2: Update/add tests** in `frontend/tests/views.test.js`:
  - If an existing test asserts the streak pill/strip, change it to assert ABSENCE.
  - Add:

```javascript
test("shell no longer renders a streak pill", () => {
  const html = shellHTML({ back: "Courses" });
  assert.doesNotMatch(html, /streak/i);
});

test("dashboard no longer renders a streak strip", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 2, reviewsDue: 0, masteryCounts: {} },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" });
  assert.doesNotMatch(html, /streak/i);
});
```

  Update any existing `shellHTML({ streakDays: ... })` test calls to `shellHTML({ back: ... })`.

- [ ] **Step 3: Run to verify the new/updated tests fail** — `cd frontend && node --test tests/views.test.js` → FAIL (streak still present).

- [ ] **Step 4: Implement**
  - `shell.js`: change signature to `export function shellHTML({ back = null })`; remove the
    `<div class="streak">…</div>` markup (and the now-unused `FLAME` import/const if it's only used
    there — check; leave it if shared).
  - `dashboard.js`: delete the `<div class="streak-strip">…</div>` line (and the `FLAME` const if
    unused after removal).
  - `app.js`: remove `const STREAK_DAYS = 12;`; remove `streakDays` from every `shellHTML({...})`
    call and from the `sessionData()` return object.
  - `courses.js` `loadLesson`: return an error shape on failure:

```javascript
export async function loadLesson({ fetch, courseId, lessonId }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}`);
  if (!resp.ok) {
    let message = "Couldn't load this lesson. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
```

  - `app.js`: add a helper and use it where lessons are loaded:

```javascript
  function lessonFailed(l) { return !l || l.error; }

  function showLessonError(message) {
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card lesson"><div class="prompt">${escapeHtml(message)}</div>` +
      `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
  }
```

  In `openLesson`, replace `if (!ui.lesson) { showCourse(); return; }` with:

```javascript
    if (lessonFailed(ui.lesson)) { showLessonError(ui.lesson && ui.lesson.error || "Couldn't load this lesson."); return; }
```

  In `startReviewSession` and `advanceAfterLesson`, change their `if (!ui.lesson) { … }` guards to
  use `lessonFailed(ui.lesson)` (keep their existing fallback to `showCourse()` there — review/advance
  failures bounce to the course, which is acceptable; only the primary `openLesson` shows the inline
  message). `escapeHtml` already exists in app.js.

- [ ] **Step 5: Run** — `cd frontend && node --test`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/shell.js frontend/src/views/dashboard.js frontend/src/app.js frontend/src/courses.js frontend/tests/views.test.js
git commit -m "feat(frontend): remove streak placeholder; surface lesson-load failures"
```

---

### Task 4: End-to-end verification + deploy

**Files:** none (verification + deploy).

- [ ] **Step 1: Full local sweep** — `.venv/bin/pytest -q` PASS; `cd frontend && node --test` PASS.

- [ ] **Step 2: Confirm Pi Claude login + load**
```
mcp__pi-ssh__exec: env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN HOME=/home/werner PATH=/home/werner/.local/bin:$PATH timeout 60 claude -p 'Reply with ONLY {"ok": true}' --output-format json --model claude-sonnet-4-6
```
Expected `is_error:false`; also `uptime`.

- [ ] **Step 3: Deploy**
```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then `mcp__pi-ssh__sudo-exec: systemctl restart claude-university` and confirm `is-active`.

- [ ] **Step 4: Real-browser check (Playwright, `http://100.99.33.106:8200/`)**
  1. Confirm the **streak pill is gone** from the top bar and there's no streak strip on a course
     dashboard.
  2. Create a tiny course; open its lesson; confirm it generates and renders (quality check did not
     false-reject), and if the lesson body contains a horizontal rule it renders as a line (not
     literal `<hr>`).
  3. (Auth path is unit-tested against the captured 401 output; not exercised live so as not to
     break the Pi login.)
  4. Remove the throwaway course on the Pi; confirm the university is empty.

- [ ] **Step 5: Confirm service active + enabled.**

---

## Self-Review

**1. Spec coverage:** auth detection (T1) + surfacing in chat/lesson-route/lesson-screen (T2, T3);
empty-lesson rejection (T2); `<hr>` (T2); streak removal (T3); e2e (T4). All map to tasks.

**2. Placeholder scan:** none — all code is concrete; the auth detection is grounded in the captured
real 401 envelope.

**3. Type consistency:** `ClaudeAuthError` (T1) is imported/caught in generation.chat_sse and
app.get_lesson (T2). `_auth_failure_reason(..., scan_text=...)` signature consistent. `loadLesson`'s
`{error}` shape (T3) is read by `lessonFailed`/`showLessonError`; a real lesson never has an `error`
key, so the discriminator is safe. The re-auth user message text is identical across chat_sse and
the lesson route.
