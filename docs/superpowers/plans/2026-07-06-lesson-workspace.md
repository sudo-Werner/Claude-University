# Lesson Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each lesson a collapsible workspace panel with a plain-text **Notes** tab (auto-saved to the Pi) and a lesson-aware **Chat** tab (streamed conversation with Claude), both persisted per-lesson and reloaded on any device.

**Architecture:** One JSON file per lesson (`content/courses/<cid>/notes/<lid>.json` = `{notes, chat, updatedAt}`) is the store. A small `backend/notes.py` loads/saves it; two REST routes (`GET`/`PUT .../workspace`) persist it; a streaming `POST .../chat` route reuses the existing SSE plumbing with a lesson-context prompt (no web search). Frontend: `notes.js` (load/save + localStorage cache), a generalized `streamChat`, and a tabbed panel rendered inside `lessonHTML` and wired in `app.js`.

**Tech Stack:** Flask + SQLite backend (`.venv/bin/pytest`), plain ES-module frontend (`node --test`), deployed to the Pi via rsync + `systemctl restart claude-university`.

## Global Constraints
- Default-deny stays intact: notes render only as a `<textarea>` value; chat text renders via `esc()` — never raw innerHTML.
- Route id validation: `course_id`/`lesson_id` must match `_ID_RE` (`^[a-z0-9-]+$`) or return 404 (prevents path traversal).
- Store size cap: reject a workspace whose serialized JSON exceeds 100 KB → HTTP 413.
- The side-chat uses `claude_client.stream` (plain streaming) — **no web search** (unlike lessons).
- Timestamps: `datetime.now(timezone.utc).isoformat()` (backend), matching `backend/events.py`.
- No new deps. Frontend `new Date()` is fine (browser); do not use secure-context-only APIs (plain HTTP over Tailscale).
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Backend workspace store (`backend/notes.py`)

**Files:**
- Create: `backend/notes.py`
- Test: `tests/test_notes.py` (create)

**Interfaces:**
- Produces: `load_workspace(content_dir, course_id, lesson_id) -> {"notes":str,"chat":list,"updatedAt":str|None}`;
  `save_workspace(content_dir, course_id, lesson_id, notes:str, chat:list) -> dict` (raises `ValueError` on bad shape, `WorkspaceTooLarge` on oversize); `class WorkspaceTooLarge(ValueError)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notes.py
import pytest
from backend import notes


def test_load_workspace_default_when_missing(tmp_path):
    assert notes.load_workspace(tmp_path, "c", "l1") == {"notes": "", "chat": [], "updatedAt": None}


def test_save_and_load_roundtrip(tmp_path):
    rec = notes.save_workspace(tmp_path, "c", "l1", "my notes",
                               [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    assert rec["notes"] == "my notes"
    assert rec["updatedAt"]
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["notes"] == "my notes"
    assert ws["chat"][1] == {"role": "assistant", "content": "yo"}


def test_save_workspace_rejects_bad_shape(tmp_path):
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", "n", [{"role": "bad", "content": "x"}])
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", 123, [])


def test_save_workspace_enforces_size_cap(tmp_path):
    with pytest.raises(notes.WorkspaceTooLarge):
        notes.save_workspace(tmp_path, "c", "l1", "x" * 200000, [])


def test_load_workspace_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "c" / "notes" / "l1.json"
    p.parent.mkdir(parents=True)
    p.write_text("not json{")
    assert notes.load_workspace(tmp_path, "c", "l1")["notes"] == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_notes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.notes'`

- [ ] **Step 3: Implement `backend/notes.py`**

```python
import json
from datetime import datetime, timezone
from pathlib import Path

_MAX_BYTES = 100_000  # ~100 KB cap on the serialized notes + chat
_EMPTY = {"notes": "", "chat": [], "updatedAt": None}


class WorkspaceTooLarge(ValueError):
    pass


def _path(content_dir, course_id, lesson_id):
    return Path(content_dir) / course_id / "notes" / f"{lesson_id}.json"


def load_workspace(content_dir, course_id, lesson_id):
    path = _path(content_dir, course_id, lesson_id)
    if not path.exists():
        return dict(_EMPTY)
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    return {
        "notes": data["notes"] if isinstance(data.get("notes"), str) else "",
        "chat": data["chat"] if isinstance(data.get("chat"), list) else [],
        "updatedAt": data.get("updatedAt"),
    }


def _valid_chat(chat):
    if not isinstance(chat, list):
        return False
    for m in chat:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return False
        if not isinstance(m.get("content"), str):
            return False
    return True


def save_workspace(content_dir, course_id, lesson_id, notes, chat):
    if not isinstance(notes, str) or not _valid_chat(chat):
        raise ValueError("invalid workspace shape")
    record = {
        "notes": notes,
        "chat": [{"role": m["role"], "content": m["content"]} for m in chat],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    blob = json.dumps(record, ensure_ascii=False)
    if len(blob.encode("utf-8")) > _MAX_BYTES:
        raise WorkspaceTooLarge("workspace too large")
    path = _path(content_dir, course_id, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(blob)
    return record
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_notes.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/notes.py tests/test_notes.py
git commit -m "feat(notes): per-lesson workspace store (notes + chat JSON, size-capped)"
```

---

### Task 2: Backend workspace routes (`GET`/`PUT .../workspace`)

**Files:**
- Modify: `backend/app.py` (add two routes near the other `/api/courses/<course_id>/lessons/<lesson_id>/...` routes; add `notes` to the `from backend import ...` line)
- Test: `tests/test_courses_api.py` (append)

**Interfaces:**
- Consumes: `notes.load_workspace`, `notes.save_workspace`, `notes.WorkspaceTooLarge` (Task 1); `courses.CONTENT_DIR`, `_ID_RE` (existing).
- Produces: `GET /api/courses/<cid>/lessons/<lid>/workspace` → workspace JSON; `PUT` same path, body `{notes, chat}` → `{updatedAt}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_courses_api.py`)

```python
def test_workspace_get_default_and_put_roundtrip(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json() == {
        "notes": "", "chat": [], "updatedAt": None}
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and r.get_json()["updatedAt"]
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["notes"] == "n" and got["chat"][0]["content"] == "hi"


def test_workspace_put_rejects_bad_and_oversize(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                      json={"notes": "n", "chat": [{"role": "x", "content": "y"}]}).status_code == 400
    assert client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                      json={"notes": "z" * 200000, "chat": []}).status_code == 413


def test_workspace_rejects_bad_ids(client):
    assert client.get("/api/courses/Bad_Id/lessons/l1/workspace").status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py -k workspace -q`
Expected: FAIL (404 for the GET/PUT because the routes don't exist yet)

- [ ] **Step 3: Add `notes` to the import in `backend/app.py`**

Change the existing line:
```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery
```
to:
```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes
```

- [ ] **Step 4: Add the routes in `backend/app.py`** (place immediately before `@app.get("/api/courses/<course_id>/reviews")`)

```python
    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def get_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        return jsonify(notes.load_workspace(courses.CONTENT_DIR, course_id, lesson_id))

    @app.put("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def put_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            record = notes.save_workspace(
                courses.CONTENT_DIR, course_id, lesson_id,
                body.get("notes", ""), body.get("chat", []),
            )
        except notes.WorkspaceTooLarge:
            return jsonify({"error": "notes too large"}), 413
        except ValueError:
            return jsonify({"error": "invalid workspace"}), 400
        return jsonify({"updatedAt": record["updatedAt"]})
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py -k workspace -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(notes): GET/PUT workspace routes"
```

---

### Task 3: Lesson-chat prompt + SSE (`generation.lesson_chat_prompt`, `lesson_chat_sse`)

**Files:**
- Modify: `backend/generation.py` (add both functions near `chat_sse`/`build_chat_prompt`)
- Test: `tests/test_generation.py` (append; the file already has the `_events()` helper and imports `claude_client`)

**Interfaces:**
- Consumes: `_sse`, `claude_client.stream`, `claude_client.ClaudeAuthError/ClaudeError` (existing).
- Produces: `lesson_chat_prompt(lesson, messages) -> str`; `lesson_chat_sse(lesson, messages, *, stream_fn) -> generator` yielding `delta`/`done`/`error` SSE frames.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_generation.py`)

```python
def test_lesson_chat_prompt_includes_lesson_context():
    lesson = {"topic": "HTTP requests", "promptHtml": "<p>what is a GET</p>",
              "solutionAns": "GET /x", "solutionNote": "method+path"}
    p = gen.lesson_chat_prompt(lesson, [{"role": "user", "content": "does http/2 change this?"}])
    assert "HTTP requests" in p
    assert "what is a GET" in p
    assert "Learner: does http/2 change this?" in p
    assert p.rstrip().endswith("You:")


def test_lesson_chat_sse_streams_delta_then_done():
    def fake_stream(prompt):
        yield "HTTP/2 keeps "
        yield "the same idea."
    lesson = {"topic": "HTTP", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    chunks = list(gen.lesson_chat_sse(lesson, [{"role": "user", "content": "q?"}], stream_fn=fake_stream))
    evs = _events(chunks)
    assert ("delta", "HTTP/2 keeps") in evs
    assert evs[-1][0] == "done"


def test_lesson_chat_sse_emits_reauth_on_auth_error():
    def failing(prompt):
        raise claude_client.ClaudeAuthError("Invalid API key")
        yield
    chunks = list(gen.lesson_chat_sse({"topic": "t"}, [{"role": "user", "content": "x"}], stream_fn=failing))
    msg = [d for (e, d) in _events(chunks) if e == "error"]
    assert msg and "re-authentication" in msg[0].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_generation.py -k lesson_chat -q`
Expected: FAIL — `AttributeError: module 'backend.generation' has no attribute 'lesson_chat_prompt'`

- [ ] **Step 3: Implement in `backend/generation.py`** (add after `build_chat_prompt`)

```python
LESSON_CHAT_SYSTEM = (
    "You are a friendly study companion helping a learner while they work through ONE "
    "lesson. They may ask questions or float side-thoughts about the lesson or a genuine "
    "tangent it sparks — answer concisely and clearly, like a knowledgeable tutor. Stay "
    "grounded in the lesson's topic; keep answers focused and short. Do not invent a new "
    "exercise or reveal the solution unless they ask for it."
)


def lesson_chat_prompt(lesson, messages):
    ctx = (
        f"Lesson topic: {lesson.get('topic', '')}\n"
        f"Lesson prompt (HTML): {lesson.get('promptHtml', '')}\n"
        f"Reference answer: {lesson.get('solutionAns', '')}\n"
        f"Why it is right: {lesson.get('solutionNote', '')}\n"
    )
    lines = [LESSON_CHAT_SYSTEM, "", "The lesson the learner is studying:", ctx, ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)


def lesson_chat_sse(lesson, messages, *, stream_fn):
    prompt = lesson_chat_prompt(lesson, messages)
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

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_generation.py -k lesson_chat -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(notes): lesson-aware chat prompt + SSE (no web search)"
```

---

### Task 4: Lesson-chat route (`POST .../chat`)

**Files:**
- Modify: `backend/app.py` (add route near the workspace routes)
- Test: `tests/test_courses_api.py` (append)

**Interfaces:**
- Consumes: `generation.lesson_chat_sse` (Task 3), `claude_client.stream`, `courses.load_lesson`, `app.response_class` (existing).
- Produces: `POST /api/courses/<cid>/lessons/<lid>/chat` body `{messages}` → SSE stream.

- [ ] **Step 1: Write the failing test** (append to `tests/test_courses_api.py`)

```python
def test_lesson_chat_route_streams(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    monkeypatch.setattr(claude_client, "stream", lambda prompt, **kw: iter(["Hello ", "world"]))
    resp = client.post(f"/api/courses/{cid}/lessons/{lesson_id}/chat",
                       json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "event: delta" in text and "Hello" in text and "event: done" in text


def test_lesson_chat_route_404_unknown_lesson(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, _ = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/lessons/nope/chat",
                       json={"messages": []}).status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py -k lesson_chat -q`
Expected: FAIL (404/405 — route missing)

- [ ] **Step 3: Add the route in `backend/app.py`** (place after the `put_workspace` route)

```python
    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/chat")
    def post_lesson_chat(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True) or {}
        sse = generation.lesson_chat_sse(lesson, body.get("messages", []), stream_fn=claude_client.stream)
        return app.response_class(sse, mimetype="text/event-stream")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py -k lesson_chat -q && .venv/bin/python -m pytest -q`
Expected: PASS (both selected tests, and the full suite green)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(notes): streaming lesson-chat route"
```

---

### Task 5: Frontend workspace data layer (`frontend/src/notes.js`)

**Files:**
- Create: `frontend/src/notes.js`
- Test: `frontend/tests/notes.test.js` (create)

**Interfaces:**
- Produces: `loadWorkspace({fetch, storage, courseId, lessonId}) -> Promise<{notes,chat,updatedAt}>`;
  `saveWorkspace({fetch, storage, courseId, lessonId, notes, chat}) -> Promise<{ok, updatedAt?|error?}>`.

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/tests/notes.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadWorkspace, saveWorkspace } from "../src/notes.js";

function fakeStorage() {
  const m = {};
  return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } };
}

test("loadWorkspace returns server data and caches it", async () => {
  const storage = fakeStorage();
  const fetch = async () => ({ ok: true, json: async () => ({ notes: "n", chat: [], updatedAt: "t" }) });
  const ws = await loadWorkspace({ fetch, storage, courseId: "c", lessonId: "l1" });
  assert.equal(ws.notes, "n");
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "n");
});

test("loadWorkspace falls back to cache when the request throws", async () => {
  const storage = fakeStorage();
  storage.setItem("ws:c:l1", JSON.stringify({ notes: "cached", chat: [], updatedAt: null }));
  const fetch = async () => { throw new Error("offline"); };
  const ws = await loadWorkspace({ fetch, storage, courseId: "c", lessonId: "l1" });
  assert.equal(ws.notes, "cached");
});

test("saveWorkspace caches first, then PUTs", async () => {
  const storage = fakeStorage();
  let url, opts;
  const fetch = async (u, o) => { url = u; opts = o; return { ok: true, json: async () => ({ updatedAt: "t2" }) }; };
  const r = await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "hi", chat: [] });
  assert.equal(url, "/api/courses/c/lessons/l1/workspace");
  assert.equal(opts.method, "PUT");
  assert.equal(r.ok, true);
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "hi");
});

test("saveWorkspace keeps the cache when the save fails", async () => {
  const storage = fakeStorage();
  const fetch = async () => { throw new Error("offline"); };
  const r = await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "keep", chat: [] });
  assert.equal(r.ok, false);
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "keep");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test frontend/tests/notes.test.js`
Expected: FAIL — cannot find module `../src/notes.js`

- [ ] **Step 3: Implement `frontend/src/notes.js`**

```javascript
const KEY = (courseId, lessonId) => `ws:${courseId}:${lessonId}`;
const EMPTY = { notes: "", chat: [], updatedAt: null };

function cacheGet(storage, courseId, lessonId) {
  try { return JSON.parse(storage.getItem(KEY(courseId, lessonId))); } catch (e) { return null; }
}
function cacheSet(storage, courseId, lessonId, ws) {
  try { storage.setItem(KEY(courseId, lessonId), JSON.stringify(ws)); } catch (e) {}
}

export async function loadWorkspace({ fetch, storage, courseId, lessonId }) {
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`);
    if (resp.ok) {
      const ws = await resp.json();
      cacheSet(storage, courseId, lessonId, ws);
      return ws;
    }
  } catch (e) {}
  return cacheGet(storage, courseId, lessonId) || { ...EMPTY };
}

export async function saveWorkspace({ fetch, storage, courseId, lessonId, notes, chat }) {
  // Optimistic: write the local cache first so a failed/offline save never loses text.
  cacheSet(storage, courseId, lessonId, { notes, chat, updatedAt: new Date().toISOString() });
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, chat }),
    });
    if (!resp.ok) return { ok: false, error: `save failed (${resp.status})` };
    const body = await resp.json();
    return { ok: true, updatedAt: body.updatedAt };
  } catch (e) {
    return { ok: false, error: "offline" };
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test frontend/tests/notes.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/notes.js frontend/tests/notes.test.js
git commit -m "feat(notes): frontend workspace load/save with localStorage cache"
```

---

### Task 6: Generalize `streamChat` for a custom endpoint

**Files:**
- Modify: `frontend/src/chat.js` (the `streamChat` function only)
- Test: `frontend/tests/chat.test.js` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `streamChat({fetch, messages, endpoint?, onDelta, onProposal?, onDone, onError?})` — `endpoint` defaults to `/api/courses/chat`; `onProposal` is now optional.

- [ ] **Step 1: Write the failing test** (append to `frontend/tests/chat.test.js`)

```javascript
function bodyFrom(str) {
  const bytes = new TextEncoder().encode(str);
  let sent = false;
  return { getReader: () => ({ read: async () => (sent ? { done: true } : (sent = true, { value: bytes, done: false })) }) };
}

test("streamChat posts to a custom endpoint and tolerates a missing onProposal", async () => {
  let url;
  const fetch = async (u) => { url = u; return { body: bodyFrom("event: delta\ndata: hi\n\nevent: done\ndata: {}\n\n") }; };
  let text = "", done = false;
  await streamChat({
    fetch, endpoint: "/api/courses/c/lessons/l1/chat", messages: [],
    onDelta: (d) => { text += d; }, onDone: () => { done = true; },
  });
  assert.equal(url, "/api/courses/c/lessons/l1/chat");
  assert.equal(text, "hi");
  assert.equal(done, true);
});
```

Note: `streamChat` must already be imported at the top of `chat.test.js` (it is, for the existing tests). If not, add `import { streamChat } from "../src/chat.js";`.

- [ ] **Step 2: Run to verify it fails**

Run: `node --test frontend/tests/chat.test.js`
Expected: FAIL — the request goes to `/api/courses/chat` (endpoint ignored) so `url` assertion fails.

- [ ] **Step 3: Update `streamChat` in `frontend/src/chat.js`**

Change the signature and the two affected lines:
```javascript
export async function streamChat({ fetch, messages, endpoint = "/api/courses/chat", onDelta, onProposal, onDone, onError }) {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
```
and in the event loop, guard the proposal callback:
```javascript
      else if (event === "proposal") { if (onProposal) onProposal(JSON.parse(data)); }
```
Leave everything else in the function unchanged.

- [ ] **Step 4: Run to verify it passes**

Run: `node --test frontend/tests/chat.test.js`
Expected: PASS (existing tests + the new one)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/chat.js frontend/tests/chat.test.js
git commit -m "refactor(chat): streamChat takes an endpoint + optional onProposal"
```

---

### Task 7: Workspace panel render (`workspaceHTML` in `lesson.js`)

**Files:**
- Modify: `frontend/src/views/lesson.js` (add `workspaceHTML` + helpers; render it inside `lessonHTML`)
- Test: `frontend/tests/views.test.js` (append; `lessonHTML` + `SAMPLE_LESSON` already imported)

**Interfaces:**
- Consumes: `esc` (already imported in `lesson.js`).
- Produces: `workspaceHTML(ws)` rendered at the end of the lesson column, driven by `state.ws = {open, tab, notes, chat, pending, saveStatus}` (all optional; defaults to a collapsed panel).

- [ ] **Step 1: Write the failing tests** (append to `frontend/tests/views.test.js`)

```javascript
test("lesson shows a collapsed workspace toggle by default", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /data-action="ws-toggle"/);
  assert.match(html, /Notes/);
  assert.doesNotMatch(html, /data-field="ws-notes"/); // collapsed: no textarea yet
});

test("open workspace shows notes textarea with escaped value", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "notes", notes: "<b>hi</b>", chat: [], pending: false, saveStatus: "saved" } });
  assert.match(html, /data-field="ws-notes"/);
  assert.match(html, /&lt;b&gt;hi&lt;\/b&gt;/); // value escaped
  assert.match(html, /saved/);
});

test("open workspace chat tab escapes message content", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "<script>x</script>" }], pending: false, saveStatus: "" } });
  assert.match(html, /data-action="ws-send"/);
  assert.doesNotMatch(html, /<script>x/);
  assert.match(html, /&lt;script&gt;x&lt;\/script&gt;/);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test frontend/tests/views.test.js`
Expected: FAIL — no `data-action="ws-toggle"` in output.

- [ ] **Step 3: Add the render code in `frontend/src/views/lesson.js`**

Add these helpers above `export function lessonHTML(...)`:
```javascript
function wsNotesHTML(w) {
  const status = { saving: "saving…", saved: "saved", offline: "offline" }[w.saveStatus] || "";
  return (
    `<div class="ws-notes">` +
    `<textarea data-field="ws-notes" placeholder="Jot your notes…">${esc(w.notes || "")}</textarea>` +
    `<div class="ws-status">${status}</div></div>`
  );
}

function wsChatHTML(w) {
  const thread = (w.chat || [])
    .map((m) => `<div class="ws-msg ws-${m.role === "user" ? "you" : "ai"}">${esc(m.content)}</div>`)
    .join("");
  const pending = w.pending ? `<div class="ws-msg ws-ai ws-typing">…</div>` : "";
  return (
    `<div class="ws-chat"><div class="ws-thread">${thread}${pending}</div>` +
    `<div class="ws-compose"><textarea data-field="ws-chat" placeholder="Ask a side question…"${w.pending ? " disabled" : ""}></textarea>` +
    `<button class="ws-send" data-action="ws-send"${w.pending ? " disabled" : ""}>Send</button></div></div>`
  );
}

function workspaceHTML(ws) {
  const w = ws || {};
  const caret = w.open ? "▾" : "▸";
  const head = `<button class="ws-toggle" data-action="ws-toggle"><span class="ws-caret">${caret}</span> Notes &amp; side-chat</button>`;
  if (!w.open) return `<section class="card workspace">${head}</section>`;
  const tabs =
    `<div class="ws-tabs">` +
    `<button class="ws-tab ${w.tab === "chat" ? "" : "on"}" data-action="ws-tab" data-tab="notes">Notes</button>` +
    `<button class="ws-tab ${w.tab === "chat" ? "on" : ""}" data-action="ws-tab" data-tab="chat">Chat</button>` +
    `</div>`;
  const body = w.tab === "chat" ? wsChatHTML(w) : wsNotesHTML(w);
  return `<section class="card workspace">${head}${tabs}${body}</section>`;
}
```

Then render it: in `lessonHTML`, immediately before the final closing `</div>` of the `.lesson-col` (right after the `<div class="nav">…</div>` block), insert:
```javascript
    ${workspaceHTML(state.ws)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test frontend/tests/views.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/lesson.js frontend/tests/views.test.js
git commit -m "feat(notes): workspace panel render (collapsible, tabs, escaped)"
```

---

### Task 8: Wire the workspace into `app.js` + styles (browser-verified)

**Files:**
- Modify: `frontend/src/app.js` (imports; `openLesson`/`startReviewSession`/`advanceAfterLesson` seed `ws`; `paintLesson` binds the controls; add helpers)
- Modify: `frontend/styles.css` (append the workspace styles)

**Interfaces:**
- Consumes: `loadWorkspace`, `saveWorkspace` (Task 5); `streamChat` with `endpoint` (Task 6); `workspaceHTML` renders from `ui.lessonState.ws` (Task 7).
- Produces: no exported API; integration only (verified in the browser on the Pi).

Note: `app.js` has no unit tests; verify via the import-resolution check and the Pi browser check.

- [ ] **Step 1: Add the import in `frontend/src/app.js`**

```javascript
import { loadWorkspace, saveWorkspace } from "./notes.js";
```
(`streamChat` is already imported from `./chat.js`.)

- [ ] **Step 2: Add workspace helpers inside `init(...)`** (near the other lesson helpers, e.g. after `paintLesson`)

```javascript
  // ---- lesson workspace (notes + side-chat) ----
  const WS_PREFS = "ws-prefs"; // remembers open/closed + active tab across lessons
  function wsPrefs() {
    try { return JSON.parse(storage.getItem(WS_PREFS)) || {}; } catch (e) { return { open: false, tab: "notes" }; }
  }
  function setWsPrefs(patch) {
    const next = { ...wsPrefs(), ...patch };
    try { storage.setItem(WS_PREFS, JSON.stringify(next)); } catch (e) {}
  }
  let wsSaveTimer = null;
  function scheduleNotesSave() {
    if (wsSaveTimer) window.clearTimeout(wsSaveTimer);
    ui.lessonState.ws.saveStatus = "saving";
    wsSaveTimer = window.setTimeout(saveWsNow, 1000);
  }
  async function saveWsNow() {
    const ls = ui.lessonState, ws = ls.ws;
    const res = await saveWorkspace({
      fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id,
      notes: ws.notes, chat: ws.chat,
    });
    if (ui.lessonState !== ls) return;               // navigated away
    ws.saveStatus = res.ok ? "saved" : "offline";
    const el = root.querySelector(".ws-status");
    if (el) el.textContent = { saving: "saving…", saved: "saved", offline: "offline" }[ws.saveStatus] || "";
  }
  async function sendWsChat() {
    const ls = ui.lessonState, ws = ls.ws;
    const ta = root.querySelector('[data-field="ws-chat"]');
    const text = ta ? ta.value.trim() : "";
    if (!text || ws.pending) return;
    ws.chat.push({ role: "user", content: text });
    ws.pending = true;
    const reply = { role: "assistant", content: "" };
    paintLesson();
    await streamChat({
      fetch,
      endpoint: `/api/courses/${ui.courseId}/lessons/${ui.lesson.id}/chat`,
      messages: ws.chat.map((m) => ({ role: m.role, content: m.content })),
      onDelta: (d) => {
        if (ui.lessonState !== ls) return;
        reply.content += d;
        const thread = root.querySelector(".ws-thread");
        if (thread) {
          let live = thread.querySelector(".ws-live");
          if (!live) { live = doc.createElement("div"); live.className = "ws-msg ws-ai ws-live"; thread.appendChild(live); }
          live.textContent = reply.content;
        }
      },
      onDone: () => {
        if (ui.lessonState !== ls) return;
        ws.pending = false;
        if (reply.content.trim()) ws.chat.push(reply);
        paintLesson();
        saveWsNow();
      },
      onError: (e) => {
        if (ui.lessonState !== ls) return;
        ws.pending = false;
        ws.chat.push({ role: "assistant", content: "⚠️ " + ((e && e.message) || "Claude is unavailable right now.") });
        paintLesson();
      },
    });
  }
```

- [ ] **Step 3: Seed `ws` when a lesson opens.** In `openLesson`, after `ui.lessonState = { ... }` is assigned and before `showLesson()`, add:

```javascript
    const prefs = wsPrefs();
    const wsData = await loadWorkspace({ fetch, storage, courseId: ui.courseId, lessonId });
    if (ui.lesson && ui.lesson.id === lessonId) {
      ui.lessonState.ws = { open: !!prefs.open, tab: prefs.tab || "notes",
                            notes: wsData.notes || "", chat: wsData.chat || [], pending: false, saveStatus: "" };
    }
```

Apply the same three-line seeding in `startReviewSession` and `advanceAfterLesson` right after each `ui.lessonState = { ... }` assignment (each also has the lesson id in scope — use `ui.lesson.id`). If `ui.lessonState.ws` is ever undefined when `paintLesson` runs, `workspaceHTML` already tolerates it (renders collapsed).

- [ ] **Step 4: Bind the controls in `paintLesson`.** At the end of `paintLesson`, add:

```javascript
    const wsToggle = view.querySelector('[data-action="ws-toggle"]');
    if (wsToggle) wsToggle.addEventListener("click", () => {
      ui.lessonState.ws.open = !ui.lessonState.ws.open;
      setWsPrefs({ open: ui.lessonState.ws.open });
      paintLesson();
    });
    view.querySelectorAll('[data-action="ws-tab"]').forEach((b) => b.addEventListener("click", () => {
      ui.lessonState.ws.tab = b.getAttribute("data-tab");
      setWsPrefs({ tab: ui.lessonState.ws.tab });
      paintLesson();
    }));
    const wsNotes = view.querySelector('[data-field="ws-notes"]');
    if (wsNotes) wsNotes.addEventListener("input", () => {
      ui.lessonState.ws.notes = wsNotes.value;
      scheduleNotesSave();
      const el = root.querySelector(".ws-status");
      if (el) el.textContent = "saving…";
    });
    const wsSend = view.querySelector('[data-action="ws-send"]');
    if (wsSend) wsSend.addEventListener("click", sendWsChat);
```

- [ ] **Step 5: Append the styles to `frontend/styles.css`**

```css
/* lesson workspace — notes + side-chat panel */
.workspace{padding:14px 16px}
.ws-toggle{width:100%; text-align:left; background:none; border:none; cursor:pointer; font:600 13px/1 inherit; color:var(--purple); display:flex; align-items:center; gap:8px}
.ws-caret{font-size:11px}
.ws-tabs{display:flex; gap:6px; margin:12px 0 10px}
.ws-tab{flex:1; padding:8px; border-radius:var(--r-sm); cursor:pointer; font:600 13px/1 inherit; border:1px solid var(--border-field); background:var(--glass-field); color:var(--text-dim)}
.ws-tab.on{background:rgba(124,106,255,.14); color:var(--purple); border-color:rgba(124,106,255,.3)}
.ws-notes textarea{width:100%; min-height:120px; resize:vertical}
.ws-status{font-size:11px; color:var(--text-faint); margin-top:6px; text-align:right}
.ws-chat{display:flex; flex-direction:column; gap:10px}
.ws-thread{display:flex; flex-direction:column; gap:8px; max-height:280px; overflow-y:auto}
.ws-msg{font-size:14px; line-height:1.5; padding:9px 12px; border-radius:12px; white-space:pre-wrap; word-break:break-word}
.ws-you{background:rgba(124,106,255,.12); color:var(--text-2); align-self:flex-end; max-width:85%}
.ws-ai{background:var(--glass-inner); color:var(--read); align-self:flex-start; max-width:90%}
.ws-typing{color:var(--text-mut)}
.ws-compose{display:flex; gap:8px; align-items:flex-end}
.ws-compose textarea{flex:1; min-height:44px; resize:vertical}
.ws-send{padding:10px 14px; border:none; border-radius:var(--r-sm); cursor:pointer; font:600 13px/1 inherit; color:#fff; background:var(--grad)}
.ws-send:disabled{opacity:.5; cursor:default}
```

- [ ] **Step 6: Import-resolution check + full suites**

Run:
```bash
for f in frontend/src/app.js frontend/src/notes.js frontend/src/views/lesson.js frontend/src/chat.js; do node -e "import('./$f').then(()=>console.log('OK '+ '$f')).catch(e=>{console.error('FAIL '+ '$f', e.message);process.exit(1)})"; done
node --test 'frontend/tests/*.test.js'
.venv/bin/python -m pytest -q
```
Expected: all `OK`, all frontend tests pass, all backend tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "feat(notes): wire lesson workspace (notes autosave + side-chat) + styles"
```

---

### Task 9: Deploy + Pi browser-verify

**Files:** none (deployment).

- [ ] **Step 1: Coordinate.** Confirm Werner is not mid-generation (check `pgrep -af "claude -p"` on the Pi is empty). Deploy is a ~3s restart.

- [ ] **Step 2: Deploy**

```bash
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' --exclude '.DS_Store' \
  --exclude '.remember/' --exclude '.superpowers/' --exclude '.claude/' --exclude '.playwright-mcp/' \
  --exclude '.pytest_cache/' --exclude '__pycache__/' --exclude 'content/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then restart: `sudo systemctl restart claude-university` and confirm `systemctl is-active` + `/api/health`.

- [ ] **Step 3: Browser-verify (throwaway course, `http://100.99.33.106:8200/`)**
  1. Create a bare throwaway course; open a lesson (it generates).
  2. Expand **Notes**, type text → see "saving…" then "saved"; reload the page → notes persist.
  3. Switch to **Chat**, ask a lesson-specific question → reply streams in and is relevant to the lesson; reload → the transcript is still there.
  4. Delete the throwaway course + its `notes/` from the Pi.

- [ ] **Step 4: Update `docs/ROADMAP.md` + memory; commit docs.**

---

## Self-Review

**Spec coverage:** store (Task 1) ✓; GET/PUT routes (Task 2) ✓; lesson-chat prompt+sse (Task 3) ✓; chat route (Task 4) ✓; frontend notes.js (Task 5) ✓; streamChat generalization (Task 6) ✓; panel render (Task 7) ✓; app wiring + CSS (Task 8) ✓; deploy/verify (Task 9) ✓. Size cap, id validation, XSS (textarea value + esc), no-web-search chat, localStorage cache, per-lesson scope — all covered.

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `load_workspace`/`save_workspace` return `{notes, chat, updatedAt}` used identically in routes and frontend; `ws` state shape `{open, tab, notes, chat, pending, saveStatus}` is consistent across `workspaceHTML` (Task 7) and `app.js` (Task 8); `streamChat({endpoint})` used in Task 8 matches the signature added in Task 6; `WorkspaceTooLarge` raised in Task 1, caught in Task 2.
