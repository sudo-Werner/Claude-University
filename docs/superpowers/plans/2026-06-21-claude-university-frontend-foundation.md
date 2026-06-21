# Claude University — Frontend Foundation & Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Werner (plain-language review):** Each task starts with a **What this is / Why / What you can verify** block in plain English — review *those* and the "Decisions for you" section below. The code beneath each step is the execution detail for whoever builds it; you don't need to read it.

**Goal:** Build the browser-side foundation — the app shell, the offline-first event buffer, the sync-to-Pi client, and the diagnostic/profile logic — everything the platform needs *except* the styled screens (which wait on the Claude design output).

**Architecture:** A single static `platform.html` loading plain ES modules — no framework, no build step. The testable logic (event buffering, sync, profile) lives in pure modules with their dependencies (storage, network, clock, id-generator) **injected**, so the same code runs in the browser and is unit-tested in Node with fakes. The browser wiring (`app.js`) supplies the real `localStorage` and `fetch`. The Pi service from Plan 1 also serves these files.

**Tech Stack:** Plain HTML + ES modules (no framework, no bundler), Node's built-in test runner (`node --test`) for the logic modules, Playwright (already available) for the real-browser end-to-end check.

## Global Constraints

- No frontend framework, no build step, no bundler — plain ES modules loaded directly.
- The event buffer is offline-first: events are written to `localStorage` instantly and flushed to the Pi in the background; a dropped connection must never lose or duplicate an event.
- Every event gets a unique `client_event_id` at creation (idempotency pairs with Plan 1's server-side dedupe).
- Testable logic modules take their dependencies as arguments (storage, fetch, clock, id) — no hidden globals — so they unit-test in Node.
- Single user (Werner). The API base URL defaults to the same origin the page is served from.
- Commit messages end with the trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## Plan sequence

This is **Plan 2 of 4**, and depends on Plan 1's API (`/api/events`, `/api/profile`). It deliberately stops short of the *styled* Dashboard and Lesson screens — those need the Claude design output and become **Plan 3**. What this plan delivers is everything underneath them: the shell, the event pipeline, and the diagnostic.

## Decisions for you (review these, not the code)

- **The diagnostic runs once, on first open**, as the very first screen. After that the app remembers your profile (stored on the Pi) and skips straight in. You can re-take it later to update preferences (a new version is saved, old ones kept).
- **Events flush to the Pi every ~15 seconds** and also immediately when you open the app — and silently keep buffering if the Pi is unreachable, flushing when it's back. (Number is easy to change.)
- **The screens in this plan are intentionally unstyled placeholders** — just enough structure to prove the data pipeline works. The real look comes from your Claude design output in Plan 3. So when you open it after this plan, it'll be plain and ugly *on purpose*.
- **The API address defaults to "wherever the page came from"** — so opening it via the Pi just works on your laptop or phone, no configuration.

## File Structure

```
frontend/
  package.json        # {"type":"module"} so .js files are ES modules in Node + browser
  platform.html       # the single-page shell (unstyled placeholders for now)
  src/
    ids.js            # client_event_id + session_id generation
    eventlog.js       # build events; read/append/clear the localStorage buffer
    sync.js           # flush the buffer to the Pi API
    profile.js        # the 6 diagnostic questions; build/save/load the profile
    app.js            # browser wiring: real localStorage + fetch + timers (not unit-tested)
  tests/
    eventlog.test.js
    sync.test.js
    profile.test.js
```

Plus a one-line change to Plan 1's `backend/app.py` (Task 5) so the Pi serves these files.

---

### Task 1: ID generation + event building

**What this is:** The smallest piece — making a single well-formed event object with a guaranteed-unique id.
**Why:** Every event needs a unique `client_event_id` so re-sending after a dropped connection is harmless (Plan 1 dedupes on it). This isolates that logic so it's dead simple to test.
**What you can verify:** Two events are never identical; an event carries the fields the Pi expects.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/ids.js`
- Create: `frontend/src/eventlog.js` (the `buildEvent` part only in this task)
- Test: `frontend/tests/eventlog.test.js`

**Interfaces:**
- Produces:
  - `frontend/src/ids.js`: `newId(prefix = "") -> string` (uses `crypto.randomUUID()`), `getSessionId(storage) -> string` (creates-and-persists a session id under key `cu_session_id` on first call).
  - `frontend/src/eventlog.js`: `buildEvent({ type, topicId = null, payload = null, sessionId, device = "web", now, newId })` → `{ client_event_id, session_id, event_type, occurred_at, device, topic_id, payload }`. `now` is a `() => Date` and `newId` is injected for testability.

- [ ] **Step 1: Write the package marker**

`frontend/package.json`:
```json
{ "type": "module" }
```

- [ ] **Step 2: Write the failing test**

`frontend/tests/eventlog.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildEvent } from "../src/eventlog.js";

const fixedNow = () => new Date("2026-06-21T10:00:00.000Z");
let counter = 0;
const fakeId = () => `id-${counter++}`;

test("buildEvent produces the fields the API expects", () => {
  counter = 0;
  const ev = buildEvent({
    type: "lesson_view",
    topicId: "p1t1",
    payload: { section: "intro" },
    sessionId: "s1",
    now: fixedNow,
    newId: fakeId,
  });
  assert.equal(ev.event_type, "lesson_view");
  assert.equal(ev.session_id, "s1");
  assert.equal(ev.topic_id, "p1t1");
  assert.deepEqual(ev.payload, { section: "intro" });
  assert.equal(ev.occurred_at, "2026-06-21T10:00:00.000Z");
  assert.equal(ev.device, "web");
  assert.equal(ev.client_event_id, "id-0");
});

test("each event gets a distinct client_event_id", () => {
  counter = 0;
  const a = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  const b = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.notEqual(a.client_event_id, b.client_event_id);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/eventlog.js`.

- [ ] **Step 4: Write minimal implementation**

`frontend/src/ids.js`:
```javascript
export function newId(prefix = "") {
  return prefix + crypto.randomUUID();
}

export function getSessionId(storage) {
  let id = storage.getItem("cu_session_id");
  if (!id) {
    id = newId("sess-");
    storage.setItem("cu_session_id", id);
  }
  return id;
}
```

`frontend/src/eventlog.js`:
```javascript
export function buildEvent({
  type,
  topicId = null,
  payload = null,
  sessionId,
  device = "web",
  now,
  newId,
}) {
  return {
    client_event_id: newId(),
    session_id: sessionId,
    event_type: type,
    occurred_at: now().toISOString(),
    device,
    topic_id: topicId,
    payload,
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/src/ids.js frontend/src/eventlog.js frontend/tests/eventlog.test.js
git commit -m "feat(frontend): event building and id generation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The offline-first buffer

**What this is:** Reading, adding to, and clearing the local list of not-yet-sent events stored in the browser.
**Why:** This is the "shock absorber" — events land here instantly so learning never waits on the network, and they stay here until the Pi confirms it has them.
**What you can verify:** Adding an event makes the buffer grow; clearing specific events leaves the rest; a fresh browser starts empty.

**Files:**
- Modify: `frontend/src/eventlog.js` (add buffer functions)
- Test: `frontend/tests/eventlog.test.js` (add buffer tests)

**Interfaces:**
- Consumes: `buildEvent` (Task 1).
- Produces (in `eventlog.js`):
  - `readBuffer(storage) -> array` (empty array if none; key `cu_event_buffer`)
  - `appendEvent(storage, event) -> void`
  - `clearEvents(storage, clientEventIds) -> void` (removes only those ids)

- [ ] **Step 1: Write the failing test (append to the existing file)**

Add to `frontend/tests/eventlog.test.js`:
```javascript
import { readBuffer, appendEvent, clearEvents } from "../src/eventlog.js";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, v),
  };
}

test("buffer starts empty", () => {
  assert.deepEqual(readBuffer(fakeStorage()), []);
});

test("appended events accumulate", () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  assert.deepEqual(readBuffer(s).map((e) => e.client_event_id), ["a", "b"]);
});

test("clearEvents removes only the named ids", () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  appendEvent(s, { client_event_id: "c" });
  clearEvents(s, ["a", "c"]);
  assert.deepEqual(readBuffer(s).map((e) => e.client_event_id), ["b"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — `readBuffer`/`appendEvent`/`clearEvents` are not exported.

- [ ] **Step 3: Write minimal implementation (append to `eventlog.js`)**

```javascript
const BUFFER_KEY = "cu_event_buffer";

export function readBuffer(storage) {
  const raw = storage.getItem(BUFFER_KEY);
  return raw ? JSON.parse(raw) : [];
}

export function appendEvent(storage, event) {
  const buffer = readBuffer(storage);
  buffer.push(event);
  storage.setItem(BUFFER_KEY, JSON.stringify(buffer));
}

export function clearEvents(storage, clientEventIds) {
  const drop = new Set(clientEventIds);
  const remaining = readBuffer(storage).filter(
    (e) => !drop.has(e.client_event_id),
  );
  storage.setItem(BUFFER_KEY, JSON.stringify(remaining));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (5 tests total).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/eventlog.js frontend/tests/eventlog.test.js
git commit -m "feat(frontend): offline-first event buffer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Flushing the buffer to the Pi

**What this is:** Taking everything in the local buffer, sending it to the Pi, and — only if the Pi confirms — removing it from the buffer.
**Why:** This is the bridge from browser to source-of-truth. The "only if confirmed" rule is what makes a dropped connection safe: nothing is cleared until it's safely stored.
**What you can verify:** A successful send empties the buffer; a failed send (Pi down) leaves everything intact to retry; an empty buffer does nothing.

**Files:**
- Create: `frontend/src/sync.js`
- Test: `frontend/tests/sync.test.js`

**Interfaces:**
- Consumes: `readBuffer`, `clearEvents` (Task 2).
- Produces: `flush({ storage, fetch, endpoint }) -> Promise<{ flushed: number, error?: string }>`. Reads the buffer; if empty returns `{ flushed: 0 }` without calling the network. Otherwise `POST`s `{ events }` to `endpoint`; on a 2xx response clears those events and returns `{ flushed: n }`; on any failure leaves the buffer and returns `{ flushed: 0, error }`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/sync.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { appendEvent, readBuffer } from "../src/eventlog.js";
import { flush } from "../src/sync.js";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, v),
  };
}

test("empty buffer flushes nothing and skips the network", async () => {
  const s = fakeStorage();
  let called = false;
  const fetch = async () => {
    called = true;
  };
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.deepEqual(res, { flushed: 0 });
  assert.equal(called, false);
});

test("successful flush empties the buffer", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  const fetch = async () => ({ ok: true, json: async () => ({ accepted: 2 }) });
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 2);
  assert.deepEqual(readBuffer(s), []);
});

test("failed flush keeps the buffer for retry", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  const fetch = async () => {
    throw new Error("network down");
  };
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 0);
  assert.ok(res.error);
  assert.equal(readBuffer(s).length, 1);
});

test("non-2xx response keeps the buffer", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  const fetch = async () => ({ ok: false, status: 500 });
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 0);
  assert.equal(readBuffer(s).length, 1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/sync.js`.

- [ ] **Step 3: Write minimal implementation**

`frontend/src/sync.js`:
```javascript
import { readBuffer, clearEvents } from "./eventlog.js";

export async function flush({ storage, fetch, endpoint }) {
  const events = readBuffer(storage);
  if (events.length === 0) return { flushed: 0 };

  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!resp.ok) return { flushed: 0, error: `HTTP ${resp.status}` };
    clearEvents(storage, events.map((e) => e.client_event_id));
    return { flushed: events.length };
  } catch (err) {
    return { flushed: 0, error: String(err) };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (9 tests total).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/sync.js frontend/tests/sync.test.js
git commit -m "feat(frontend): sync buffer to Pi with retry safety

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The diagnostic + profile

**What this is:** The six diagnostic questions as data, plus turning your answers into the profile object and saving/loading it from the Pi.
**Why:** This configures how the whole platform teaches you. Keeping the questions as data (not hard-coded screens) means the look can come from your design later while the logic is settled and tested now.
**What you can verify:** There are exactly six questions covering the six settings; answering them produces a correct profile object; saving then loading returns the same profile.

**Files:**
- Create: `frontend/src/profile.js`
- Test: `frontend/tests/profile.test.js`

**Interfaces:**
- Produces (in `profile.js`):
  - `DIAGNOSTIC` — array of 6 `{ key, question, options: [{ label, value }] }`, keys: `contentOrder`, `stuckStrategy`, `wrongAnswerFeedback`, `sessionStyle`, `lessonStructure`, `analogies`.
  - `buildProfile(answers) -> object` where `answers` maps each `key` to a chosen `value`; returns `{ contentOrder, stuckStrategy, wrongAnswerFeedback, sessionStyle, lessonStructure, analogies }`.
  - `saveProfile({ fetch, endpoint, profile }) -> Promise<object>` (`POST` to `/api/profile`).
  - `loadProfile({ fetch, endpoint }) -> Promise<object|null>` (`GET`; returns the saved `data` object, or `null` if none).

- [ ] **Step 1: Write the failing test**

`frontend/tests/profile.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { DIAGNOSTIC, buildProfile, saveProfile, loadProfile } from "../src/profile.js";

test("diagnostic covers exactly the six profile settings", () => {
  const keys = DIAGNOSTIC.map((q) => q.key).sort();
  assert.deepEqual(keys, [
    "analogies",
    "contentOrder",
    "lessonStructure",
    "sessionStyle",
    "stuckStrategy",
    "wrongAnswerFeedback",
  ]);
  for (const q of DIAGNOSTIC) {
    assert.ok(q.question.length > 0);
    assert.ok(q.options.length >= 2);
  }
});

test("buildProfile maps answers to the config object", () => {
  const answers = {
    contentOrder: "theory_first",
    stuckStrategy: "push",
    wrongAnswerFeedback: "hint",
    sessionStyle: "deep_block",
    lessonStructure: "top_down",
    analogies: true,
  };
  assert.deepEqual(buildProfile(answers), answers);
});

test("saveProfile posts to the endpoint", async () => {
  let sent;
  const fetch = async (url, opts) => {
    sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ id: 1 }) };
  };
  await saveProfile({ fetch, endpoint: "/api/profile", profile: { analogies: true } });
  assert.equal(sent.url, "/api/profile");
  assert.deepEqual(sent.body, { analogies: true });
});

test("loadProfile returns the saved data or null", async () => {
  const withData = async () => ({ ok: true, json: async () => ({ data: { analogies: false } }) });
  assert.deepEqual(await loadProfile({ fetch: withData, endpoint: "/api/profile" }), {
    analogies: false,
  });
  const empty = async () => ({ ok: true, json: async () => ({}) });
  assert.equal(await loadProfile({ fetch: empty, endpoint: "/api/profile" }), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/profile.js`.

- [ ] **Step 3: Write minimal implementation**

`frontend/src/profile.js`:
```javascript
export const DIAGNOSTIC = [
  {
    key: "contentOrder",
    question: "When learning something new, what works better for you?",
    options: [
      { label: "Give me the rule/theory first, then code", value: "theory_first" },
      { label: "Show me examples; I'll figure out the rule", value: "examples_first" },
    ],
  },
  {
    key: "stuckStrategy",
    question: "You're stuck 20 minutes into a lesson. What helps most?",
    options: [
      { label: "Push through — confusion is part of learning", value: "push" },
      { label: "Review the prerequisite first", value: "review_prereq" },
      { label: "Skip it and come back later", value: "skip" },
    ],
  },
  {
    key: "wrongAnswerFeedback",
    question: "You get a quiz question wrong. What do you want?",
    options: [
      { label: "Show the correct answer immediately", value: "immediate" },
      { label: "Give a hint and let me try again", value: "hint" },
      { label: "Just flag it wrong — I'll work it out", value: "self" },
    ],
  },
  {
    key: "sessionStyle",
    question: "Given a free 2-hour block, how do you prefer to learn?",
    options: [
      { label: "One deep 2-hour session on one topic", value: "deep_block" },
      { label: "Several short sprints across topics", value: "sprints" },
    ],
  },
  {
    key: "lessonStructure",
    question: "Starting a new lesson, where do you like to begin?",
    options: [
      { label: "Big picture first, then zoom into detail", value: "top_down" },
      { label: "Smallest building block first, build up", value: "bottom_up" },
    ],
  },
  {
    key: "analogies",
    question: "Do analogies (e.g. 'a neural net is like the brain') help you?",
    options: [
      { label: "Yes — they help me grasp things faster", value: true },
      { label: "No — I prefer direct explanation", value: false },
    ],
  },
];

export function buildProfile(answers) {
  return {
    contentOrder: answers.contentOrder,
    stuckStrategy: answers.stuckStrategy,
    wrongAnswerFeedback: answers.wrongAnswerFeedback,
    sessionStyle: answers.sessionStyle,
    lessonStructure: answers.lessonStructure,
    analogies: answers.analogies,
  };
}

export async function saveProfile({ fetch, endpoint, profile }) {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  return resp.json();
}

export async function loadProfile({ fetch, endpoint }) {
  const resp = await fetch(endpoint);
  const body = await resp.json();
  return body && body.data ? body.data : null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (13 tests total).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/profile.js frontend/tests/profile.test.js
git commit -m "feat(frontend): diagnostic questions and profile logic

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: App shell, browser wiring, serve from Pi, prove the loop

**What this is:** A bare `platform.html` that wires the tested modules to the real browser (real storage, real network, a 15-second flush timer), the Pi serving that page, and a real-browser test proving an event travels browser → Pi → database.
**Why:** This is the moment the pieces become a running thing you can open. It's unstyled on purpose — the proof here is *the data pipeline works end-to-end*, not how it looks.
**What you can verify:** You open the page from the Pi, it logs a "page opened" event, and within seconds that event is in the Pi's database — confirmed by reading it back through the API.

**Files:**
- Create: `frontend/src/app.js`
- Create: `frontend/platform.html`
- Modify: `backend/app.py` (add static serving of the `frontend/` folder)
- Test: `backend/` — add `tests/test_static.py`; plus a Playwright real-browser check (manual verification steps)

**Interfaces:**
- Consumes: `getSessionId`, `buildEvent`, `appendEvent` (Tasks 1–2), `flush` (Task 3), `loadProfile`/`DIAGNOSTIC`/`buildProfile`/`saveProfile` (Task 4); the Plan 1 API.
- Produces: `frontend/src/app.js` exporting `init({ window, fetch })` which: resolves the session id, logs a `session_start` event, starts a 15s flush loop + flush-on-load, and renders either the diagnostic (if no profile) or a placeholder "you're set up" message. `backend/app.py` serves `platform.html` at `/` and `src/*` files.

- [ ] **Step 1: Write the failing backend static-serving test**

`backend/tests/test_static.py`:
```python
def test_root_serves_platform_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!doctype html" in resp.data.lower()


def test_src_module_served(client):
    resp = client.get("/src/sync.js")
    assert resp.status_code == 200
    assert b"export" in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/../tests/test_static.py -v` (from project root: `pytest tests/test_static.py -v`)
Expected: FAIL — `/` returns 404 (no static route yet).

- [ ] **Step 3: Add static serving to `backend/app.py`**

Add these imports at the top of `backend/app.py`:
```python
from pathlib import Path

from flask import send_from_directory
```

Inside `create_app`, before `return app`, add:
```python
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "platform.html")

    @app.get("/src/<path:filename>")
    def src_files(filename):
        return send_from_directory(frontend_dir / "src", filename)
```

- [ ] **Step 4: Create the shell and wiring (so the static test has a file to serve)**

`frontend/platform.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Claude University</title>
  </head>
  <body>
    <main id="app">Loading…</main>
    <script type="module">
      import { init } from "/src/app.js";
      init({ window, fetch: window.fetch.bind(window) });
    </script>
  </body>
</html>
```

`frontend/src/app.js`:
```javascript
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile } from "./profile.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const FLUSH_INTERVAL_MS = 15000;

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const sessionId = getSessionId(storage);

  const log = (type, opts = {}) =>
    appendEvent(
      storage,
      buildEvent({ type, sessionId, now: () => new Date(), newId, ...opts }),
    );

  log("session_start");

  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const app = window.document.getElementById("app");
  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  // Placeholder rendering — real screens arrive with the design (Plan 3).
  app.textContent = profile
    ? "Profile loaded — ready. (Styled screens come next.)"
    : "First run — diagnostic goes here. (Styled screens come next.)";
}
```

- [ ] **Step 5: Run the backend test to verify it passes**

Run: `pytest tests/test_static.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run every test (frontend + backend)**

Run: `cd frontend && node --test` → PASS (13 tests).
Run: `pytest -v` (from project root) → PASS (all backend tests incl. static).

- [ ] **Step 7: Real-browser end-to-end check (Playwright)**

With the Plan 1 service running locally (`waitress-serve --port=8000 --call backend.app:create_app`):
1. Open `http://localhost:8000/` in a browser (Playwright `browser_navigate`).
2. Wait ~2s, then take a snapshot — the page should show the "first run" or "ready" placeholder text (confirms `app.js` loaded and ran).
3. Read the events API back:
   ```bash
   curl -s 'http://localhost:8000/api/events?type=session_start'
   ```
   Expected: a `session_start` event is present — proving the full loop browser → buffer → flush → Pi → database works.

- [ ] **Step 8: Commit**

```bash
git add frontend/platform.html frontend/src/app.js backend/app.py tests/test_static.py
git commit -m "feat(frontend): app shell, browser wiring, served from Pi

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage (frontend-foundation slice):**
- Offline-first buffer → Tasks 2–3. ✓
- Sync to Pi, idempotent + retry-safe → Task 3 (pairs with Plan 1 dedupe). ✓
- Diagnostic captured as the first-run flow; profile stored/versioned on the Pi → Task 4 + Plan 1's profile store. ✓
- Static frontend served by the Pi (one URL, any device) → Task 5. ✓
- No framework / no build step → enforced throughout. ✓
- *Correctly deferred to Plan 3:* the styled Dashboard and Lesson screens, the session timer UI, FSRS/mastery — all need the design output and/or the learning mechanics.

**2. Placeholder scan:** The only "placeholder" is the deliberate unstyled UI text in Task 5, called out as intentional. No TBD/TODO/"handle edge cases"; every code step is complete. ✓

**3. Type consistency:** `buildEvent` signature (Task 1) reused unchanged in `app.js` (Task 5); `readBuffer`/`appendEvent`/`clearEvents` (Task 2) consumed by `sync.flush` (Task 3) and `app.js`; `flush` signature consistent Tasks 3 and 5; `loadProfile`/`DIAGNOSTIC`/`buildProfile` (Task 4) consumed by `app.js`. The injected-dependency pattern (`storage`, `fetch`, `now`, `newId`) is consistent across every module. ✓
