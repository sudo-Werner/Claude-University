# Empty Start & Add-Course Composer (Slice 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Werner (plain-language review):** Each task opens with a **What / Why / Verify** line. Two small changes — empty the university, fix the add-course composer — plus a deploy.

**Goal:** Ship an empty default university (no seeded course) and a usable, intentional "Add a course" composer, with no backend logic changes.

**Architecture:** Delete the seeded ML course and make the API tests build their own temporary fixture course instead of depending on it. Rebuild the broken composer in `views/chat.js` + `styles.css` as a roomy textarea with a right-sized Send below it (a `.chat-input`-scoped `width:auto` override, mirroring the existing `.nav .btn-primary` precedent). No backend logic touched.

**Tech Stack:** Flask + SQLite (backend tests), plain ES modules + `node --test` (frontend), Playwright for the real-browser check.

## Global Constraints

- No backend course-creation / chat / generation logic changes — content removal, a test-fixture rework, and CSS/markup only.
- No new dependencies; plain ES modules, no framework.
- The composer keeps the `data-field="chat"` and `data-action="send"` hooks so `app.js` wiring is unchanged.
- The Send fix is scoped to `.chat-input .btn-primary` — the shared `.btn-primary` rule is not modified.
- Use existing design tokens (`--glass-field`, `--border-field`, `--r-md`, `--text`) for the composer.
- The Pi is **not** a git checkout — deploy by rsync from Mac (exclude `.venv/`, `backend/data/`), then `sudo systemctl restart claude-university`. Remove the ML course directory on the Pi too.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure

- `content/courses/machine-learning/` (delete) — the seeded course; removed so the platform ships empty.
- `tests/test_courses_api.py` (modify) — the three seed-dependent GET/list tests build their own temp fixture course; the rest unchanged.
- `frontend/src/views/chat.js` (modify) — composer markup becomes a textarea + a right-aligned Send row; same data hooks.
- `frontend/styles.css` (modify) — `.chat-col` bounded/centered; `.chat-input` restyled to a column composer; scoped Send `width:auto`.
- `frontend/tests/chat.test.js` (modify) — add a small `chatHTML` structural test (composer hooks + escaping).

---

### Task 1: Empty start — remove the seeded course, make API tests self-contained

**What / Why / Verify:** Delete the seeded Machine Learning course so the university opens empty, and rework the API tests (which used it as a fixture) to create their own temporary course. *Verify:* the backend suite passes with no ML course on disk; the GET/list/lesson endpoints are exercised against a self-created fixture.

**Files:**
- Delete: `content/courses/machine-learning/` (the whole directory)
- Modify: `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `courses.write_course(content_dir, proposal)` and `courses.CONTENT_DIR` (existing); the `client` fixture (Flask test client) from `tests/conftest.py`.
- Produces: no new code; self-contained API tests.

- [ ] **Step 1: Delete the seeded course**

```bash
git rm -r content/courses/machine-learning
```

- [ ] **Step 2: Run the suite to see the seed-dependent tests fail**

Run: `.venv/bin/pytest tests/test_courses_api.py -v`
Expected: FAIL — `test_list_courses_includes_machine_learning`, `test_get_course_manifest`, `test_get_lesson_and_404s` fail (no `machine-learning` course). This confirms exactly which tests depended on the seed.

- [ ] **Step 3: Rework the three seed-dependent tests**

Replace the first three test functions (`test_list_courses_includes_machine_learning`, `test_get_course_manifest`, `test_get_lesson_and_404s`) in `tests/test_courses_api.py` with the versions below. Keep `test_post_course_creates_and_lists`, `test_post_course_rejects_missing_fields`, and `test_routes_reject_illegal_ids` as they are. Add `import json` at the top.

```python
import json


def _fixture_course(courses, root):
    """Create a course manifest plus one written lesson file in a temp content dir.

    Writing the lesson file means the lesson GET serves it from disk — it does NOT
    hit the just-in-time generator (which would call real Claude). A lesson id that
    is NOT in the manifest returns 404 from ensure_lesson before any generation.
    """
    manifest = courses.write_course(root, {
        "title": "Test Topic",
        "subtitle": "a test course",
        "brief": "ctx",
        "modules": [{"title": "Module One", "lessons": [{"title": "Lesson One"}]}],
    })
    lesson_id = manifest["modules"][0]["lessons"][0]["id"]
    lesson = {
        "id": lesson_id, "courseId": manifest["id"], "topic": "Topic One",
        "step": 1, "totalSteps": 1, "eyebrow": "EXERCISE",
        "promptHtml": "p", "hintHtml": "h", "solutionAns": "a", "solutionNote": "n",
    }
    (root / manifest["id"] / "lessons" / f"{lesson_id}.json").write_text(json.dumps(lesson))
    return manifest, lesson_id


def test_list_courses_returns_created_course(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)

    listed = client.get("/api/courses").get_json()["courses"]
    found = next(c for c in listed if c["id"] == manifest["id"])
    assert found["title"] == "Test Topic"
    assert found["progress"]["total"] == 1
    assert found["nextLesson"]["id"] == lesson_id


def test_get_course_manifest(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)

    resp = client.get(f"/api/courses/{manifest['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["modules"][0]["title"] == "Module One"


def test_get_lesson_and_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    ok = client.get(f"/api/courses/{cid}/lessons/{lesson_id}")
    assert ok.status_code == 200
    assert ok.get_json()["topic"] == "Topic One"
    # unknown lesson id is not in the manifest -> 404 (no generation)
    assert client.get(f"/api/courses/{cid}/lessons/nope").status_code == 404
    # unknown course -> 404
    assert client.get("/api/courses/nope").status_code == 404
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `.venv/bin/pytest tests/test_courses_api.py -v` then `.venv/bin/pytest -q`
Expected: PASS — all `test_courses_api.py` tests green, and the whole backend suite green with no `machine-learning` course present.

- [ ] **Step 5: Commit**

```bash
git add tests/test_courses_api.py
git rm -r content/courses/machine-learning
git commit -m "feat: start with an empty university; make course API tests self-contained

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(If `git rm` in Step 1 already staged the deletion, `git add tests/test_courses_api.py` plus that staged deletion are committed together; the `git rm` line above is harmless if already removed.)

---

### Task 2: Rebuild the add-course composer

**What / Why / Verify:** The composer's Send button (base `.btn-primary` is `width:100%`) collapses the textarea to a sliver. Rebuild it as a roomy multi-line textarea with a right-aligned, normal-sized Send below, in a bounded centered column. *Verify (unit):* `chatHTML` renders the composer hooks and escapes message content; all frontend tests pass. *Verify (real app):* deferred to Task 3.

**Files:**
- Modify: `frontend/src/views/chat.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/chat.test.js`

**Interfaces:**
- Consumes: nothing new.
- Produces: `chatHTML(messages, { pending })` unchanged signature; markup keeps `textarea[data-field="chat"]` and `button[data-action="send"]`. CSS adds a scoped `.chat-input .btn-primary { width:auto }`.

- [ ] **Step 1: Write the failing test** — append to `frontend/tests/chat.test.js`:

```javascript
import { chatHTML } from "../src/views/chat.js";

test("chatHTML renders the composer with input + send hooks", () => {
  const html = chatHTML([], {});
  assert.match(html, /data-field="chat"/);
  assert.match(html, /data-action="send"/);
  assert.match(html, /Add a course/);
});

test("chatHTML escapes message content", () => {
  const html = chatHTML([{ role: "user", content: "<b>hi</b>" }], {});
  assert.doesNotMatch(html, /<b>hi<\/b>/);
  assert.match(html, /&lt;b&gt;hi/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/chat.test.js`
Expected: FAIL — `chatHTML` is not yet imported/exported in a way these assertions pass (the import line is new; if `chatHTML` already renders these hooks the structural test may pass, but the escaping test is new coverage — run to confirm the file imports cleanly and both pass after Step 3). If both already pass against the current `chat.js`, proceed; the redesign in Step 3 must keep them passing.

- [ ] **Step 3: Rebuild the composer markup** — replace the body of `frontend/src/views/chat.js`'s `chatHTML` (keep the `esc` and `bubble` helpers above it unchanged):

```javascript
export function chatHTML(messages, { pending = false } = {}) {
  const thread = messages.map(bubble).join("");
  const dots = pending ? `<div class="msg claude pending">…</div>` : "";
  return `
    <div class="chat-col">
      <div class="greeting"><h1>Add a course</h1><span>Tell Claude what you want to learn</span></div>
      <div class="chat-thread">${thread}${dots}</div>
      <div class="chat-input">
        <textarea data-field="chat" rows="3"
          placeholder="e.g. intermediate linear algebra for ML, ~3 hours a week — I know basic calculus"></textarea>
        <div class="chat-send"><button class="btn-primary" data-action="send">Send</button></div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 4: Replace the composer styles** — in `frontend/styles.css`, replace the existing chat block (the `.chat-col` / `.chat-thread` / `.msg*` / `.chat-input` / `.chat-input textarea` rules) with:

```css
/* =================  COURSE-CREATION CHAT  ================= */
.chat-col{display:flex; flex-direction:column; gap:16px}
.chat-thread{display:flex; flex-direction:column; gap:10px}
.msg{max-width:85%; padding:11px 14px; border-radius:var(--r-lg); font-size:14px; line-height:1.5; white-space:pre-wrap}
.msg.me{align-self:flex-end; background:var(--grad); color:#fff}
.msg.claude{align-self:flex-start; background:var(--glass-card-2); border:1px solid var(--border-glass); color:var(--text)}
.msg.pending{color:var(--text-mut)}

/* composer: roomy multi-line input, Send below it on the right */
.chat-input{display:flex; flex-direction:column; gap:10px}
.chat-input textarea{
  width:100%; min-height:96px; resize:vertical;
  background:var(--glass-field); border:1px solid var(--border-field); border-radius:var(--r-md);
  padding:13px 15px; font:15px/1.5 inherit; color:var(--text);
}
.chat-send{display:flex; justify-content:flex-end}
.chat-input .btn-primary{width:auto; padding:12px 26px}

@media (min-width:760px){
  .chat-col{max-width:680px; margin:0 auto; width:100%}
}
```

(The earlier chat block also contained `.card.proposal` and `.card.lesson.loading` rules from Slice 2 — leave those exactly as they are; only the `.chat-col`/`.chat-thread`/`.msg*`/`.chat-input` rules change.)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && node --test`
Expected: PASS — all suites including the two new `chat.test.js` assertions.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/chat.js frontend/styles.css frontend/tests/chat.test.js
git commit -m "fix(frontend): rebuild add-course composer (roomy textarea, right-sized Send)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Verify in the browser + deploy

**What / Why / Verify:** Confirm the empty home and the fixed composer in a real browser, then ship to the Pi (removing the ML course there too). *Verify:* the Pi opens to an empty university; the composer is usable at phone and desktop widths; a chat still streams a reply.

**Files:** none changed (verification + deploy).

- [ ] **Step 1: Full local test sweep**

Run: `.venv/bin/pytest -q` → PASS (no ML course). `cd frontend && node --test` → PASS.

- [ ] **Step 2: Run the app locally**

Run: `.venv/bin/waitress-serve --port=8222 --call backend.app:create_app` (background).

- [ ] **Step 3: Real-browser check (Playwright)**

1. `browser_navigate` to `http://localhost:8222/`; if the diagnostic shows, complete it → home.
2. Confirm the home is **empty** — only the "Add a course" card (no ML course).
3. Click "Add a course"; `browser_resize` to a phone width (~390px) and a desktop width (~1100px); snapshot each — confirm the composer shows a **roomy textarea with a normal-sized Send beneath it, right-aligned** (no collapsed sliver, no full-width Send), bounded/centered on desktop.
4. Type a short request and Send; confirm a streamed reply renders above the composer (this exercises the unchanged wiring).
5. Stop the local server.

- [ ] **Step 4: Deploy to the Pi**

```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then remove the seeded course on the Pi (rsync without `--delete` won't remove it):
```
mcp__pi-ssh__exec: rm -rf /home/werner/claude_university/content/courses/machine-learning
mcp__pi-ssh__sudo-exec: systemctl restart claude-university
```

- [ ] **Step 5: Verify on the Pi**

```
mcp__pi-ssh__exec: systemctl is-active claude-university
mcp__pi-ssh__exec: curl -s http://localhost:8200/api/courses
```
Expected: service `active`; `/api/courses` returns `{"courses": []}` (empty university). Optionally open `http://100.99.33.106:8200/` and confirm the empty home + fixed composer over Tailscale.

---

## Self-Review

**1. Spec coverage:**
- Remove seeded ML course (repo + Pi) → Task 1 (repo) + Task 3 Step 4 (Pi). ✓
- API tests reworked to self-create a fixture → Task 1. ✓
- Composer: bounded centered column; roomy textarea; Send below-right, normal-sized; scoped `width:auto` fix → Task 2. ✓
- Keep `data-field="chat"` / `data-action="send"` hooks → Task 2 markup + the structural test. ✓
- Use existing tokens; no shared-button change; no backend logic change → Task 2 (scoped rule, tokens) and the absence of any backend edit. ✓
- Browser verify at phone+desktop, empty home, working chat; deploy → Task 3. ✓
- *Correctly unchanged:* home view (already renders a clean 0-course state), bubbles/SSE/proposal/loading, streak/FSRS/login-longevity.

**2. Placeholder scan:** No "TBD/TODO". Task 2 Step 2 explains that the structural assertions may already pass against current `chat.js` — that's a real note about a redesign-keeps-passing test, not a placeholder; the escaping assertion is new coverage and the redesign must keep both green.

**3. Type consistency:** `chatHTML(messages, { pending })` signature is unchanged and matches its `app.js` call site (`chatHTML(ui.chat.messages, { pending: ui.chat.pending })`). The `.chat-input .btn-primary { width:auto }` override mirrors the existing `.nav .btn-primary { flex:1; width:auto }` precedent. `courses.write_course` and `courses.CONTENT_DIR` used in the test fixture match their Slice 2 definitions. The fixture writes a lesson file so the lesson GET serves from disk (no generator/real-Claude call); an unknown lesson id returns 404 via `ensure_lesson` before generation.
