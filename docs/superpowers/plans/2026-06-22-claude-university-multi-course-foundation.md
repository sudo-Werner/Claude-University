# Claude University — Multi-Course Foundation (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Werner (plain-language review):** Each task opens with a **What / Why / Verify** line in plain English — read those. The code beneath is execution detail for whoever builds it.

**Goal:** Turn the single hardcoded-course app into a multi-course university — courses stored as JSON on the Pi, a course-grid home screen, per-course progress derived from events, and a home → course → lesson navigation hierarchy — with the existing ML content migrated in as the first course.

**Architecture:** Course content lives as JSON files on the Pi (`content/courses/<id>/course.json` + `lessons/*.json`), served by new read-only Flask endpoints. Progress is derived on read from the event log (no progress table); events gain a `course_id` column. The frontend stays plain ES modules — a new `courses.js` fetch layer and `home.js` view, with `app.js` rewritten from a two-tab model into a screen hierarchy.

**Tech Stack:** Flask + SQLite (backend), plain HTML + ES modules with `node --test` (frontend), Playwright for the real-browser check. No framework, no build step.

## Global Constraints

- No frontend framework, no build step, no bundler — plain ES modules loaded directly.
- Single user (Werner). API base URL defaults to the page's own origin.
- Testable logic takes its dependencies as arguments (storage, fetch, conn, content_dir) — no hidden globals.
- Content is read-only in this slice. Progress derives from events; events remain the single source of truth.
- Course storage is JSON files on the Pi (writable later by Slice 2's generator), not DB rows.
- The "Add course" button is an inert placeholder (the Slice 2 seam).
- Match the existing warm light-glass styles and CSS tokens (`--glass-card-2`, `--border-glass`, `--r-xl`, `--text`, `--text-mut`, `--purple`, `--grad`). The brief's "dark theme" was superseded by the implemented design — follow the code, not the brief.
- Commit messages end with the trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure

**Backend**
- `backend/schema.sql` (modify) — add `course_id` column + index to `events`.
- `backend/db.py` (modify) — idempotent migration that adds `course_id` to a pre-existing DB.
- `backend/events.py` (modify) — persist `course_id` on insert.
- `backend/courses.py` (create) — read manifests/lessons from disk; derive progress + next lesson; list courses.
- `backend/app.py` (modify) — three read endpoints for courses/lessons.
- `content/courses/machine-learning/course.json` (create) — the first course manifest.
- `content/courses/machine-learning/lessons/ml-m3-l2.json` (create) — migrated lesson body.

**Frontend**
- `frontend/src/eventlog.js` (modify) — `buildEvent` gains `courseId`.
- `frontend/src/courses.js` (create) — `listCourses`/`loadCourse`/`loadLesson` fetch helpers.
- `frontend/src/views/home.js` (create) — `homeHTML(courses)` course grid.
- `frontend/src/views/shell.js` (modify) — context header with optional back control; tabs removed.
- `frontend/src/app.js` (modify) — screen-hierarchy state machine and wiring.
- `frontend/src/seed.js` (delete) — content now lives on the Pi.
- `frontend/styles.css` (modify) — course-grid styles.

**Tests**
- `tests/test_courses.py` (create) — content loading + progress derivation.
- `tests/test_courses_api.py` (create) — the three endpoints against the seeded ML course.
- `tests/test_events.py` (modify) — `course_id` round-trips.
- `frontend/tests/courses.test.js` (create) — fetch helpers.
- `frontend/tests/home.test.js` (create) — `homeHTML`.
- `frontend/tests/eventlog.test.js` (modify) — `courseId` field.
- `frontend/tests/views.test.js` (modify) — drop `seed.js`, use inline fixtures, update shell test.

---

### Task 1: `course_id` on events (schema + migration + insert)

**What / Why / Verify:** Give every event an optional course tag so progress can be counted per course. *Verify:* an event saved with a course id reads back with it, and an old database gains the column without losing data.

**Files:**
- Modify: `backend/schema.sql`
- Modify: `backend/db.py`
- Modify: `backend/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces: `events` rows carry `course_id TEXT` (nullable); `events.insert_events` reads `ev.get("course_id")`; `db.init_db` adds the column to a pre-existing DB if missing.

- [ ] **Step 1: Write the failing test** — append to `tests/test_events.py`:

```python
def test_insert_persists_course_id(conn):
    from backend import events, queries

    events.insert_events(conn, [{
        "client_event_id": "ce-course-1",
        "session_id": "s1",
        "event_type": "lesson_completed",
        "occurred_at": "2026-06-22T19:00:00+00:00",
        "course_id": "machine-learning",
        "topic_id": "ml-m3-l2",
    }])
    rows = queries.query_events(conn, event_type="lesson_completed")
    assert rows[0]["course_id"] == "machine-learning"
    assert rows[0]["topic_id"] == "ml-m3-l2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_events.py::test_insert_persists_course_id -v`
Expected: FAIL — `KeyError`/`sqlite3.OperationalError` (no `course_id` column).

- [ ] **Step 3: Add the column to `backend/schema.sql`** — inside the `events` table, after the `topic_id` line:

```sql
    topic_id        TEXT,
    course_id       TEXT,
```

And after the existing event indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_events_course   ON events(course_id);
```

- [ ] **Step 4: Add the idempotent migration to `backend/db.py`** — replace `init_db` with:

```python
def init_db(conn):
    conn.executescript(SCHEMA_PATH.read_text())
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "course_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN course_id TEXT")
```

- [ ] **Step 5: Persist `course_id` in `backend/events.py`** — update the INSERT in `insert_events` to include the column and value:

```python
        cur = conn.execute(
            """INSERT OR IGNORE INTO events
               (client_event_id, session_id, device, topic_id, course_id,
                event_type, occurred_at, received_at, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["client_event_id"],
                ev["session_id"],
                ev.get("device"),
                ev.get("topic_id"),
                ev.get("course_id"),
                ev["event_type"],
                ev["occurred_at"],
                received_at,
                json.dumps(payload) if payload is not None else None,
            ),
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_events.py -v`
Expected: PASS (all existing event tests + the new one).

- [ ] **Step 7: Commit**

```bash
git add backend/schema.sql backend/db.py backend/events.py tests/test_events.py
git commit -m "feat(backend): course_id on events with idempotent migration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Course content files + manifest/lesson loading

**What / Why / Verify:** Move the ML content out of the frontend seed and into stored course files, and add the code that reads them. *Verify:* the loader returns the ML course's structure and a lesson's body; unknown ids return nothing.

**Files:**
- Create: `content/courses/machine-learning/course.json`
- Create: `content/courses/machine-learning/lessons/ml-m3-l2.json`
- Create: `backend/courses.py`
- Test: `tests/test_courses.py`

**Interfaces:**
- Produces (in `backend/courses.py`):
  - `CONTENT_DIR` — `Path` to `content/courses` at the repo root.
  - `load_manifest(content_dir, course_id) -> dict | None`
  - `load_lesson(content_dir, course_id, lesson_id) -> dict | None`
  - `flatten_lessons(manifest) -> list[{"id","title","moduleTitle"}]` in module-then-lesson order.

- [ ] **Step 1: Create the manifest** `content/courses/machine-learning/course.json`:

```json
{
  "id": "machine-learning",
  "title": "Machine Learning",
  "subtitle": "From fundamentals to neural networks",
  "modules": [
    {
      "id": "m3",
      "title": "Neural Networks",
      "lessons": [
        { "id": "ml-m3-l2", "title": "Backpropagation, intuitively" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Create the lesson body** `content/courses/machine-learning/lessons/ml-m3-l2.json` (migrated from `seed.js` `SAMPLE_LESSON`):

```json
{
  "id": "ml-m3-l2",
  "courseId": "machine-learning",
  "topic": "Backpropagation",
  "step": 4,
  "totalSteps": 5,
  "eyebrow": "EXERCISE",
  "promptHtml": "A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>. With learning rate <code>η = 0.1</code>, write the gradient-descent update for <code>w</code>.",
  "hintHtml": "Gradient descent moves <em>against</em> the gradient: <span class=\"mono\">w ← w − η · ∂L/∂w</span>",
  "solutionAns": "w ← w − (0.1 × 0.4) = w − 0.04",
  "solutionNote": "Each step subtracts the learning rate times the gradient — a small move downhill on the loss."
}
```

- [ ] **Step 3: Write the failing test** `tests/test_courses.py`:

```python
import json


def _make_course(tmp_path):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "A demo course",
        "modules": [
            {"id": "m1", "title": "Module One", "lessons": [
                {"id": "l1", "title": "Lesson One"},
                {"id": "l2", "title": "Lesson Two"},
            ]},
        ],
    }))
    (root / "demo" / "lessons" / "l1.json").write_text(json.dumps({
        "id": "l1", "courseId": "demo", "topic": "One", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "p", "hintHtml": "h",
        "solutionAns": "a", "solutionNote": "n",
    }))
    return root


def test_load_manifest_and_lesson(tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    manifest = courses.load_manifest(root, "demo")
    assert manifest["title"] == "Demo"
    lesson = courses.load_lesson(root, "demo", "l1")
    assert lesson["topic"] == "One"
    assert courses.load_manifest(root, "nope") is None
    assert courses.load_lesson(root, "demo", "nope") is None


def test_flatten_lessons_keeps_order_and_module(tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    flat = courses.flatten_lessons(courses.load_manifest(root, "demo"))
    assert [l["id"] for l in flat] == ["l1", "l2"]
    assert flat[0]["moduleTitle"] == "Module One"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_courses.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.courses`.

- [ ] **Step 5: Write `backend/courses.py`:**

```python
import json
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "courses"


def load_manifest(content_dir, course_id):
    path = Path(content_dir) / course_id / "course.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_lesson(content_dir, course_id, lesson_id):
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def flatten_lessons(manifest):
    out = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            out.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "moduleTitle": module["title"],
            })
    return out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_courses.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add content/courses backend/courses.py tests/test_courses.py
git commit -m "feat(backend): course content store and manifest/lesson loading

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Progress derivation + course listing

**What / Why / Verify:** Compute, from the event log, how far a course is and which lesson is next; list all courses with that progress. *Verify:* a course with no completed lessons reports 0% and its first lesson as next; completing a lesson advances both.

**Files:**
- Modify: `backend/courses.py`
- Test: `tests/test_courses.py`

**Interfaces:**
- Consumes: `load_manifest`, `flatten_lessons` (Task 2); the `events` table (`event_type='lesson_completed'`, `course_id`, `topic_id` = lesson id).
- Produces (in `backend/courses.py`):
  - `completed_lesson_ids(conn, course_id) -> set[str]`
  - `course_progress(conn, content_dir, course_id) -> {"done","total","pct","nextLesson"} | None` where `nextLesson` is `{"id","title","moduleTitle"} | None`.
  - `list_courses(conn, content_dir) -> list[{"id","title","subtitle","progress":{"done","total","pct"},"nextLesson","reviewsDue"}]`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_courses.py`:

```python
def test_progress_starts_at_zero_and_points_at_first(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    p = courses.course_progress(conn, root, "demo")
    assert p == {"done": 0, "total": 2, "pct": 0,
                 "nextLesson": {"id": "l1", "title": "Lesson One", "moduleTitle": "Module One"}}


def test_completing_a_lesson_advances_progress(conn, tmp_path):
    from backend import courses, events
    root = _make_course(tmp_path)
    events.insert_events(conn, [{
        "client_event_id": "ce-1", "session_id": "s1",
        "event_type": "lesson_completed", "occurred_at": "2026-06-22T19:00:00+00:00",
        "course_id": "demo", "topic_id": "l1",
    }])
    p = courses.course_progress(conn, root, "demo")
    assert p["done"] == 1
    assert p["pct"] == 50
    assert p["nextLesson"]["id"] == "l2"


def test_list_courses_returns_summary(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    listed = courses.list_courses(conn, root)
    assert len(listed) == 1
    summary = listed[0]
    assert summary["id"] == "demo"
    assert summary["progress"] == {"done": 0, "total": 2, "pct": 0}
    assert summary["nextLesson"]["id"] == "l1"
    assert summary["reviewsDue"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_courses.py -v`
Expected: FAIL — `AttributeError: module 'backend.courses' has no attribute 'course_progress'`.

- [ ] **Step 3: Add the functions to `backend/courses.py`:**

```python
def completed_lesson_ids(conn, course_id):
    rows = conn.execute(
        "SELECT DISTINCT topic_id FROM events "
        "WHERE event_type = 'lesson_completed' AND course_id = ?",
        (course_id,),
    ).fetchall()
    return {r["topic_id"] for r in rows if r["topic_id"]}


def course_progress(conn, content_dir, course_id):
    manifest = load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    lessons = flatten_lessons(manifest)
    done_ids = completed_lesson_ids(conn, course_id)
    done = sum(1 for lesson in lessons if lesson["id"] in done_ids)
    total = len(lessons)
    pct = round(done / total * 100) if total else 0
    next_lesson = next((lesson for lesson in lessons if lesson["id"] not in done_ids), None)
    return {"done": done, "total": total, "pct": pct, "nextLesson": next_lesson}


def list_courses(conn, content_dir):
    content_dir = Path(content_dir)
    summaries = []
    if not content_dir.exists():
        return summaries
    for child in sorted(content_dir.iterdir()):
        if not (child / "course.json").exists():
            continue
        manifest = load_manifest(content_dir, child.name)
        progress = course_progress(conn, content_dir, child.name)
        summaries.append({
            "id": manifest["id"],
            "title": manifest["title"],
            "subtitle": manifest.get("subtitle", ""),
            "progress": {k: progress[k] for k in ("done", "total", "pct")},
            "nextLesson": progress["nextLesson"],
            "reviewsDue": 0,
        })
    return summaries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_courses.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/courses.py tests/test_courses.py
git commit -m "feat(backend): per-course progress and next-lesson from events

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Course/lesson API endpoints

**What / Why / Verify:** Expose the course list, a course's structure, and a lesson's body over HTTP. *Verify:* hitting the endpoints returns the ML course with progress, its manifest, and a lesson; unknown ids return 404.

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `courses.list_courses`, `courses.load_manifest`, `courses.load_lesson`, `courses.CONTENT_DIR` (Tasks 2–3).
- Produces: `GET /api/courses` → `{"courses":[...]}`; `GET /api/courses/<course_id>` → manifest or 404; `GET /api/courses/<course_id>/lessons/<lesson_id>` → lesson or 404.

- [ ] **Step 1: Write the failing test** `tests/test_courses_api.py`:

```python
def test_list_courses_includes_machine_learning(client):
    resp = client.get("/api/courses")
    assert resp.status_code == 200
    courses = resp.get_json()["courses"]
    ml = next(c for c in courses if c["id"] == "machine-learning")
    assert ml["title"] == "Machine Learning"
    assert ml["progress"]["total"] >= 1
    assert ml["nextLesson"]["id"] == "ml-m3-l2"


def test_get_course_manifest(client):
    resp = client.get("/api/courses/machine-learning")
    assert resp.status_code == 200
    assert resp.get_json()["modules"][0]["title"] == "Neural Networks"


def test_get_lesson_and_404s(client):
    ok = client.get("/api/courses/machine-learning/lessons/ml-m3-l2")
    assert ok.status_code == 200
    assert ok.get_json()["topic"] == "Backpropagation"
    assert client.get("/api/courses/machine-learning/lessons/nope").status_code == 404
    assert client.get("/api/courses/nope").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_courses_api.py -v`
Expected: FAIL — `/api/courses` returns 404 (no route yet).

- [ ] **Step 3: Add the routes to `backend/app.py`** — update the import line and add the routes before `frontend_dir = ...`:

Change the import:

```python
from backend import db, events, profile, queries, courses
```

Add the routes inside `create_app`:

```python
    @app.get("/api/courses")
    def get_courses():
        conn = db.get_connection(path)
        try:
            result = courses.list_courses(conn, courses.CONTENT_DIR)
        finally:
            conn.close()
        return jsonify({"courses": result})

    @app.get("/api/courses/<course_id>")
    def get_course(course_id):
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        return jsonify(manifest)

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>")
    def get_lesson(course_id, lesson_id):
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_courses_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the whole backend suite**

Run: `pytest -v`
Expected: PASS (all backend tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(backend): course and lesson read endpoints

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `buildEvent` carries `courseId`

**What / Why / Verify:** Let the browser stamp events with the course they happened in, matching the new column. *Verify:* an event built without a course has `course_id: null`; with one, it carries it.

**Files:**
- Modify: `frontend/src/eventlog.js`
- Test: `frontend/tests/eventlog.test.js`

**Interfaces:**
- Produces: `buildEvent({ type, topicId?, courseId?, payload?, sessionId, device?, now, newId })` → event object now including `course_id`.

- [ ] **Step 1: Write the failing test** — append to `frontend/tests/eventlog.test.js`:

```javascript
test("buildEvent includes course_id (null by default, set when given)", () => {
  counter = 0;
  const a = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.equal(a.course_id, null);
  const b = buildEvent({ type: "x", courseId: "machine-learning", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.equal(b.course_id, "machine-learning");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/eventlog.test.js`
Expected: FAIL — `a.course_id` is `undefined`, not `null`.

- [ ] **Step 3: Update `buildEvent` in `frontend/src/eventlog.js`:**

```javascript
export function buildEvent({
  type,
  topicId = null,
  courseId = null,
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
    course_id: courseId,
    payload,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/eventlog.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/eventlog.js frontend/tests/eventlog.test.js
git commit -m "feat(frontend): stamp events with course_id

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `courses.js` fetch helpers

**What / Why / Verify:** A small client layer that fetches the course list, a course, and a lesson from the new endpoints. *Verify:* each helper calls the right URL and returns the parsed body (or null on a missing resource).

**Files:**
- Create: `frontend/src/courses.js`
- Test: `frontend/tests/courses.test.js`

**Interfaces:**
- Produces (in `frontend/src/courses.js`):
  - `listCourses({ fetch, endpoint = "/api/courses" }) -> Promise<array>` (returns `body.courses` or `[]`).
  - `loadCourse({ fetch, courseId }) -> Promise<object|null>` (`GET /api/courses/<id>`; null on non-2xx).
  - `loadLesson({ fetch, courseId, lessonId }) -> Promise<object|null>` (`GET /api/courses/<id>/lessons/<lessonId>`; null on non-2xx).

- [ ] **Step 1: Write the failing test** `frontend/tests/courses.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { listCourses, loadCourse, loadLesson } from "../src/courses.js";

test("listCourses returns the courses array", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ courses: [{ id: "machine-learning" }] }) };
  };
  const result = await listCourses({ fetch, endpoint: "/api/courses" });
  assert.equal(url, "/api/courses");
  assert.deepEqual(result, [{ id: "machine-learning" }]);
});

test("listCourses defaults to [] when none", async () => {
  const fetch = async () => ({ ok: true, json: async () => ({}) });
  assert.deepEqual(await listCourses({ fetch }), []);
});

test("loadCourse fetches the manifest by id", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ id: "machine-learning", modules: [] }) };
  };
  const c = await loadCourse({ fetch, courseId: "machine-learning" });
  assert.equal(url, "/api/courses/machine-learning");
  assert.equal(c.id, "machine-learning");
});

test("loadLesson fetches by course and lesson id, null on miss", async () => {
  let url;
  const ok = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ id: "ml-m3-l2" }) };
  };
  const lesson = await loadLesson({ fetch: ok, courseId: "machine-learning", lessonId: "ml-m3-l2" });
  assert.equal(url, "/api/courses/machine-learning/lessons/ml-m3-l2");
  assert.equal(lesson.id, "ml-m3-l2");

  const missing = async () => ({ ok: false, status: 404 });
  assert.equal(await loadLesson({ fetch: missing, courseId: "x", lessonId: "y" }), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/courses.test.js`
Expected: FAIL — cannot find `../src/courses.js`.

- [ ] **Step 3: Write `frontend/src/courses.js`:**

```javascript
export async function listCourses({ fetch, endpoint = "/api/courses" }) {
  const resp = await fetch(endpoint);
  const body = await resp.json();
  return body.courses || [];
}

export async function loadCourse({ fetch, courseId }) {
  const resp = await fetch(`/api/courses/${courseId}`);
  if (!resp.ok) return null;
  return resp.json();
}

export async function loadLesson({ fetch, courseId, lessonId }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}`);
  if (!resp.ok) return null;
  return resp.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/courses.test.js`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/courses.js frontend/tests/courses.test.js
git commit -m "feat(frontend): course/lesson fetch helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `home.js` course-grid view + styles

**What / Why / Verify:** The university home — a card per course (title, progress, continue) plus an inert "Add a course" card. *Verify:* it renders a card per course with its progress and a continue control, and an add-course button.

**Files:**
- Create: `frontend/src/views/home.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/home.test.js`

**Interfaces:**
- Consumes: course summaries from `listCourses` (Task 6) — `{id, title, subtitle, progress:{done,total,pct}, nextLesson, reviewsDue}`.
- Produces: `homeHTML(courses) -> string`. Each course renders a `<button class="course-card" data-course="<id>">`; the add card is `<button ... data-action="add-course">`.

- [ ] **Step 1: Write the failing test** `frontend/tests/home.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { homeHTML } from "../src/views/home.js";

const ML = {
  id: "machine-learning",
  title: "Machine Learning",
  subtitle: "From fundamentals to neural networks",
  progress: { done: 1, total: 4, pct: 25 },
  nextLesson: { id: "ml-m3-l2", title: "Backpropagation, intuitively", moduleTitle: "Neural Networks" },
  reviewsDue: 0,
};

test("home renders a card per course with progress and continue", () => {
  const html = homeHTML([ML]);
  assert.match(html, /data-course="machine-learning"/);
  assert.match(html, /Machine Learning/);
  assert.match(html, /1 of 4 lessons/);
  assert.match(html, /width:25%/);
  assert.match(html, /Continue/);
});

test("home always shows the add-course card", () => {
  assert.match(homeHTML([]), /data-action="add-course"/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/home.test.js`
Expected: FAIL — cannot find `../src/views/home.js`.

- [ ] **Step 3: Write `frontend/src/views/home.js`:**

```javascript
function courseCard(c) {
  return `
    <button class="course-card" data-course="${c.id}">
      <div class="course-title">${c.title}</div>
      <div class="course-sub">${c.subtitle}</div>
      <div class="bar"><i style="width:${c.progress.pct}%"></i></div>
      <div class="course-meta">${c.progress.done} of ${c.progress.total} lessons · ${c.reviewsDue} reviews due</div>
      <span class="course-continue">Continue →</span>
    </button>`;
}

export function homeHTML(courses) {
  const cards = courses.map(courseCard).join("");
  const count = courses.length;
  return `
    <div class="home">
    <div class="greeting"><h1>Your university</h1><span>${count} course${count === 1 ? "" : "s"}</span></div>
    <div class="course-grid">
      ${cards}
      <button class="course-card add-course" data-action="add-course">
        <span class="add-plus">+</span>
        <div class="course-title">Add a course</div>
        <div class="course-sub">Tell Claude what you want to learn</div>
      </button>
    </div>
    </div>
  `;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/home.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Add the course-grid styles** — append to `frontend/styles.css`:

```css
/* =================  UNIVERSITY HOME (course grid)  ================= */
.home{display:flex; flex-direction:column; gap:16px}
.course-grid{display:flex; flex-direction:column; gap:14px}
.course-card{display:block; width:100%; text-align:left; font:inherit; cursor:pointer; color:var(--text);
  background:var(--glass-card-2); backdrop-filter:blur(26px) saturate(1.6); -webkit-backdrop-filter:blur(26px) saturate(1.6);
  border:1px solid var(--border-glass); border-radius:var(--r-xl); padding:22px; box-shadow:var(--sh-card)}
.course-title{font-size:18px; font-weight:600; letter-spacing:-.01em}
.course-sub{color:var(--text-mut); font-size:13px; margin:3px 0 14px}
.course-meta{color:var(--text-mut); font-size:13px; margin-top:10px}
.course-continue{display:inline-block; margin-top:12px; color:var(--purple-deep); font-weight:600; font-size:14px}
.course-card.add-course{display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
  border-style:dashed; border-color:rgba(124,106,255,.40); background:var(--glass-stat); color:var(--text-mut)}
.add-plus{font-size:30px; line-height:1; color:var(--purple); margin-bottom:6px}

@media (min-width:760px){
  .course-grid{display:grid; grid-template-columns:repeat(2,1fr); gap:18px; align-items:start}
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/home.js frontend/styles.css frontend/tests/home.test.js
git commit -m "feat(frontend): university home course grid

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Navigation hierarchy — shell, app wiring, retire the seed

**What / Why / Verify:** Replace the two-tab model with home → course → lesson navigation, feed the screens from the API, and delete the now-unused `seed.js`. *Verify (unit):* the shell renders a back control only when given one, and all frontend unit tests pass. *Verify (real app):* deferred to Task 9.

**Files:**
- Modify: `frontend/src/views/shell.js`
- Modify: `frontend/src/app.js`
- Delete: `frontend/src/seed.js`
- Test: `frontend/tests/views.test.js` (update — drop `seed.js`, use inline fixtures, update the shell test)

**Interfaces:**
- Consumes: `homeHTML` (Task 7), `listCourses`/`loadCourse`/`loadLesson` (Task 6), `buildEvent` with `courseId` (Task 5), `dashboardHTML`/`lessonHTML`/`diagnosticHTML`/`timerView`/profile helpers (existing).
- Produces: `shellHTML({ streakDays, back = null }) -> string` (renders a `data-action="nav-back"` button only when `back` is truthy; no `data-tab` controls). `app.js` `init({ window, fetch })` drives `ui.screen` ∈ `home|course|lesson`.

- [ ] **Step 1: Update the shell test** — replace the `shell shows both tabs...` test in `frontend/tests/views.test.js` with:

```javascript
test("shell shows the streak; back control only when given", () => {
  const home = shellHTML({ streakDays: 12 });
  assert.match(home, /12/);
  assert.match(home, /id="view"/);
  assert.doesNotMatch(home, /data-action="nav-back"/);

  const inCourse = shellHTML({ streakDays: 12, back: "Courses" });
  assert.match(inCourse, /data-action="nav-back"/);
  assert.match(inCourse, /Courses/);
});
```

- [ ] **Step 2: Replace the `seed.js` import in `frontend/tests/views.test.js`** — delete the line `import { DASHBOARD_SEED, SAMPLE_LESSON } from "../src/seed.js";` and add inline fixtures after the other imports:

```javascript
const DASHBOARD_SEED = {
  topic: "Backpropagation, intuitively",
  sub: "Module 3 · Neural Networks · Lesson 2",
  durationMin: 90, progressPct: 30, lessonsDone: 12, lessonsTotal: 40,
  reviewsDue: 8, streakDays: 12,
};
const SAMPLE_LESSON = {
  step: 4, totalSteps: 5, topic: "Backpropagation", eyebrow: "EXERCISE",
  promptHtml: "A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>.",
  hintHtml: "Gradient descent moves <em>against</em> the gradient.",
  solutionAns: "w ← w − 0.04",
  solutionNote: "A small move downhill on the loss.",
};
```

(The dashboard and lesson tests below keep using `DASHBOARD_SEED`/`SAMPLE_LESSON` unchanged. The `/w − 0.04/` and `/12 of 40 lessons/` assertions still match these fixtures.)

- [ ] **Step 3: Run the view test to verify it fails**

Run: `cd frontend && node --test tests/views.test.js`
Expected: FAIL — `shellHTML` still renders tabs / the new shell test's `nav-back` assertions fail.

- [ ] **Step 4: Rewrite `frontend/src/views/shell.js`:**

```javascript
const FLAME = `<svg class="flame" viewBox="0 0 24 24" fill="none"><path d="M12 2c1 3-1 4-1 6a3 3 0 006 0c0-1.5-1-2.5-1-4 2 1.5 4 4 4 8a8 8 0 11-16 0c0-4 3-6 4-8 .5 1 1 1.5 2 2 1-1 1.5-2 1-4z" fill="#e0892f"/></svg>`;

export function shellHTML({ streakDays, back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${back}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <div class="streak">${FLAME}${streakDays}</div>
    </header>
    ${backBtn}
    <div id="view"></div>
  `;
}
```

- [ ] **Step 5: Add a back-control style** — append to `frontend/styles.css`:

```css
.nav-back-top{align-self:flex-start; background:none; border:none; font:600 14px/1 inherit; cursor:pointer;
  color:var(--text-mut); padding:2px 0}
.nav-back-top:hover{color:var(--text)}
```

- [ ] **Step 6: Rewrite `frontend/src/app.js`:**

```javascript
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { listCourses, loadCourse, loadLesson } from "./courses.js";
import { shellHTML } from "./views/shell.js";
import { homeHTML } from "./views/home.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML } from "./views/lesson.js";
import { diagnosticHTML } from "./views/diagnostic.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const COURSES_ENDPOINT = "/api/courses";
const FLUSH_INTERVAL_MS = 15000;
const SESSION_MIN = 90;
const STREAK_DAYS = 12; // placeholder until a stats endpoint exists

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const doc = window.document;
  const sessionId = getSessionId(storage);

  const log = (type, { courseId = null, topicId = null, payload = null } = {}) =>
    appendEvent(
      storage,
      buildEvent({ type, sessionId, courseId, topicId, payload, now: () => new Date(), newId }),
    );
  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });

  log("session_start");
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const root = doc.getElementById("app");

  const ui = {
    screen: "home",
    courseId: null,
    manifest: null,
    summary: null,
    lesson: null,
    lessonState: { answer: "", hintVisible: false, solutionRevealed: false },
    timer: { running: false, elapsed: 0, intervalId: null },
    diagnostic: {},
  };

  // ---- diagnostic (unchanged flow, now lands on the home) ----
  function showDiagnostic() {
    root.innerHTML = diagnosticHTML(ui.diagnostic);
    root.querySelectorAll("[data-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        let v = btn.getAttribute("data-value");
        if (v === "true") v = true;
        else if (v === "false") v = false;
        ui.diagnostic[btn.getAttribute("data-q")] = v;
        showDiagnostic();
      });
    });
    root.querySelector('[data-action="finish-diagnostic"]').addEventListener("click", async () => {
      const profile = buildProfile(ui.diagnostic);
      log("diagnostic_completed", { payload: profile });
      await saveProfile({ fetch, endpoint: PROFILE_ENDPOINT, profile });
      await doFlush();
      showHome();
    });
  }

  // ---- home ----
  async function showHome() {
    ui.screen = "home";
    ui.courseId = null;
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS });
    const view = root.querySelector("#view");
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    view.innerHTML = homeHTML(courses);
    view.querySelectorAll("[data-course]").forEach((card) => {
      card.addEventListener("click", () => openCourse(card.getAttribute("data-course")));
    });
    view.querySelector('[data-action="add-course"]').addEventListener("click", () => {
      log("add_course_clicked");
      window.alert("Course creation is coming soon.");
    });
  }

  // ---- course session screen ----
  async function refreshSummary() {
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    ui.summary = courses.find((c) => c.id === ui.courseId) || null;
  }

  async function openCourse(courseId) {
    ui.courseId = courseId;
    ui.manifest = await loadCourse({ fetch, courseId });
    await refreshSummary();
    log("course_opened", { courseId });
    showCourse();
  }

  function sessionData() {
    const next = ui.summary && ui.summary.nextLesson;
    const p = ui.summary ? ui.summary.progress : { done: 0, total: 0, pct: 0 };
    return {
      topic: next ? next.title : "Course complete",
      sub: next ? `${next.moduleTitle} · ${ui.manifest.title}` : ui.manifest.title,
      durationMin: SESSION_MIN,
      progressPct: p.pct,
      lessonsDone: p.done,
      lessonsTotal: p.total,
      reviewsDue: ui.summary ? ui.summary.reviewsDue : 0,
      streakDays: STREAK_DAYS,
    };
  }

  function paintCourse() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(sessionData(), timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startLesson);
    view.querySelector('[data-action="review"]').addEventListener("click", () =>
      log("review_opened", { courseId: ui.courseId }),
    );
  }

  function showCourse() {
    ui.screen = "course";
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintCourse();
  }

  // ---- lesson ----
  async function startLesson() {
    const next = ui.summary && ui.summary.nextLesson;
    if (!next) return;
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: next.id });
    if (!ui.lesson) return;
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
    log("lesson_view", { courseId: ui.courseId, topicId: next.id });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  function showLesson() {
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintLesson();
  }

  function paintLesson() {
    const view = root.querySelector("#view");
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState);
    const ta = view.querySelector('[data-field="answer"]');
    ta.addEventListener("input", () => {
      ui.lessonState.answer = ta.value;
      const sel = ta.selectionStart;
      paintLesson();
      const ta2 = root.querySelector('[data-field="answer"]');
      ta2.focus();
      ta2.setSelectionRange(sel, sel);
    });
    view.querySelector('[data-action="toggle-hint"]').addEventListener("click", () => {
      ui.lessonState.hintVisible = !ui.lessonState.hintVisible;
      if (ui.lessonState.hintVisible) log("hint_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      paintLesson();
    });
    view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
      if (!ui.lessonState.answer.trim()) return;
      if (!ui.lessonState.solutionRevealed)
        log("solution_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      ui.lessonState.solutionRevealed = true;
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
    view.querySelector('[data-action="continue"]').addEventListener("click", async () => {
      log("lesson_completed", { courseId: ui.courseId, topicId: ui.lesson.id });
      await doFlush();
      await refreshSummary(); // progress advances; next lesson moves on
      showCourse();
    });
  }

  function startTimer() {
    ui.timer.running = true;
    log("session_timer_start", { courseId: ui.courseId });
    ui.timer.intervalId = window.setInterval(() => {
      ui.timer.elapsed += 1;
      if (ui.timer.elapsed >= TOTAL_SECONDS) {
        window.clearInterval(ui.timer.intervalId);
        ui.timer.running = false;
        log("session_timer_complete", { courseId: ui.courseId });
      }
      if (ui.screen === "course") paintCourse();
    }, 1000);
  }

  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  if (profile) showHome();
  else showDiagnostic();
}
```

- [ ] **Step 7: Delete the seed module**

Run: `git rm frontend/src/seed.js`
Confirm nothing else imports it: `grep -rn "seed.js" frontend/` → only matches should be gone (no source references; the test now uses inline fixtures).

- [ ] **Step 8: Run the full frontend suite**

Run: `cd frontend && node --test`
Expected: PASS (all suites — views, home, courses, eventlog, sync, timer, profile, reveal, ids).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app.js frontend/src/views/shell.js frontend/styles.css frontend/tests/views.test.js
git rm frontend/src/seed.js
git commit -m "feat(frontend): home -> course -> lesson navigation, retire seed

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification + deploy to the Pi

**What / Why / Verify:** Prove the whole loop in a real browser, then ship it to the Pi and confirm it runs there. *Verify:* open from the Pi → see the ML course → enter it → do a lesson → "continue" lands on the next lesson; a `course_id`-stamped `lesson_completed` event is in the Pi's database.

**Files:** none changed (verification + deploy only).

- [ ] **Step 1: Full test sweep (local)**

Run: `pytest -v` (repo root) → PASS (all backend incl. courses + courses_api + events).
Run: `cd frontend && node --test` → PASS (all frontend suites).

- [ ] **Step 2: Run the app locally**

Run: `waitress-serve --port=8200 --call backend.app:create_app` (background).

- [ ] **Step 3: Real-browser check (Playwright)**

1. `browser_navigate` to `http://localhost:8200/`.
2. If the diagnostic shows (fresh profile), answer all six and finish — expect the **home** screen.
3. Snapshot the home: a "Machine Learning" course card with progress and a Continue control, plus an "Add a course" card.
4. Click the Machine Learning card → snapshot the **course** screen (Today's session = "Backpropagation, intuitively", phase bar, Start session).
5. Click "Start session" → snapshot the **lesson** (the backprop exercise). Type an answer, reveal the solution, click "Continue".
6. Back on the course screen, confirm progress advanced (lessons done incremented; next topic changed or "Course complete").
7. Click "Add a course" → confirm the "coming soon" alert (the inert placeholder).
8. Read the events back:
   `curl -s 'http://localhost:8200/api/events?type=lesson_completed'`
   Expected: an event with `"course_id":"machine-learning"` and `"topic_id":"ml-m3-l2"`.

- [ ] **Step 4: Stop the local server.**

- [ ] **Step 5: Push, then deploy on the Pi** (per project rule — verify on the Pi, restart the service):

```bash
git push
mcp__pi-ssh__exec: cd ~/Claude_Education && git pull
mcp__pi-ssh__exec: sudo systemctl restart claude-university
mcp__pi-ssh__exec: systemctl is-active claude-university
mcp__pi-ssh__exec: curl -s http://localhost:8200/api/courses
```

Expected: service `active`; `/api/courses` returns the Machine Learning course. The `_migrate` step (Task 1) adds `course_id` to the Pi's existing database on restart without data loss.

- [ ] **Step 6: Confirm from the real Pi URL** (insecure-context note: test on the actual Pi URL, not localhost crypto assumptions): open the Pi address in a browser, confirm the home renders and a lesson round-trips, then read `/api/events?type=lesson_completed` on the Pi to confirm the event landed in its database.

---

## Self-Review

**1. Spec coverage:**
- File-based content store (manifest + lesson files) → Task 2. ✓
- Migration of `seed.js` ML content into the first course → Tasks 2 (files) + 8 (delete seed). ✓
- `course_id` on events; progress derived (no progress table) → Tasks 1, 3. ✓
- `lesson_completed` as the explicit completion signal → Tasks 3 (counted), 8 (emitted). ✓
- Read endpoints: list / manifest / lesson → Task 4. ✓
- University-home equal course grid → Task 7. ✓
- Dashboard repurposed as per-course session screen → Task 8 (`sessionData` feeds existing `dashboardHTML`). ✓
- Lesson flow fed by stored content → Task 8 (`loadLesson` → `lessonHTML`). ✓
- Navigation hierarchy replacing the two tabs; streak in header; timer inside the session → Task 8. ✓
- Inert "Add course" seam → Tasks 7 (button) + 8 (alert + `add_course_clicked` event). ✓
- "Continue where you left off" derived from progress → Tasks 3 (`nextLesson`) + 8 (Start/Continue). ✓
- *Correctly deferred:* Claude/generation (Slice 2); the FSRS engine (`reviewsDue` is a constant 0); multi-user.

**2. Placeholder scan:** No "TBD/TODO". The two deliberate constants — `STREAK_DAYS` and `reviewsDue: 0` — are real values with comments, matching the spec's deferral of streak/SR logic, not unfinished code. ✓

**3. Type consistency:** `buildEvent({courseId})` (Task 5) is called with `courseId` throughout `app.js` (Task 8). `list_courses` summary shape `{id,title,subtitle,progress:{done,total,pct},nextLesson,reviewsDue}` (Task 3) is exactly what `homeHTML` (Task 7) and `sessionData` (Task 8) consume. `nextLesson` `{id,title,moduleTitle}` from `flatten_lessons` (Task 2) flows unchanged through progress (Task 3) into `sessionData`'s `sub`/`topic` (Task 8). `lesson_completed` + `topic_id`=lesson id is written (Task 8) and counted (Task 3) consistently. `shellHTML({streakDays, back})` (Task 8) matches every call site. ✓
