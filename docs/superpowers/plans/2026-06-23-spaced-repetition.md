# Spaced Repetition (Slice 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add spaced repetition — an Anki-style recall rating on lesson finish drives an SM-2 schedule (derived from `lesson_reviewed` events), a real per-course "reviews due" count, and a Review flow that re-presents due lessons through the existing lesson screen.

**Architecture:** A new pure `backend/srs.py` computes SM-2 state by replaying a lesson's `lesson_reviewed` events; `courses.list_courses` reports a real `reviewsDue` and a new `GET /api/courses/<id>/reviews` lists due lessons. The frontend replaces the lesson's "Continue" with a four-button recall rating (logs `lesson_reviewed`), and the dashboard's Review button runs a review session over the due lessons. No schema change.

**Tech Stack:** Flask + SQLite, plain ES modules (`node --test`), Playwright for the browser check.

## Global Constraints

- No schema change — `lesson_reviewed` reuses the existing `events` table (`event_type` + `course_id` + `topic_id` + `payload`).
- Schedule is **derived from the event log**, never stored — same principle as Slice 1 progress.
- Algorithm is **SM-2**; recall ratings map `again→1, hard→3, good→4, easy→5`; grade `<3` resets repetitions and makes the lesson **due the same day**.
- A lesson counts as "done" if it has ≥1 `lesson_completed` **or** `lesson_reviewed` event (back-compatible).
- Course/lesson route ids are validated `^[a-z0-9-]+$` (existing guard); the new reviews route follows it.
- Testable logic takes `conn`, `content_dir`, and an injectable `today` — no hidden globals; unit tests never call real Claude.
- The Pi is not a git checkout — deploy via rsync + `systemctl restart claude-university`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure

- `backend/srs.py` (create) — SM-2 scheduler + due-lesson computation (pure + event-reading).
- `backend/courses.py` (modify) — `completed_lesson_ids` counts both event types; `list_courses` reports real `reviewsDue` (lazy import of `srs` to avoid an import cycle).
- `backend/app.py` (modify) — add `GET /api/courses/<course_id>/reviews`.
- `frontend/src/views/lesson.js` (modify) — recall rating control when the solution is revealed.
- `frontend/src/courses.js` (modify) — `loadReviews` client helper.
- `frontend/src/app.js` (modify) — rating handler + review-session flow.
- `frontend/styles.css` (modify) — rating-button styles.
- Tests: `tests/test_srs.py`, `tests/test_courses.py` (extend), `tests/test_courses_api.py` (extend), `frontend/tests/views.test.js` (extend), `frontend/tests/courses.test.js` (extend).

---

### Task 1: `srs.py` — SM-2 scheduler + due computation

**What / Why / Verify:** The scheduling brain. *Verify:* SM-2 intervals progress 1 → 6 → round(prev·EF); EF updates and floors at 1.3; `again` resets and is due today; due-lesson computation reflects synthetic review events against an injected "today."

**Files:**
- Create: `backend/srs.py`
- Test: `tests/test_srs.py`

**Interfaces:**
- Consumes: `courses.load_manifest`, `courses.flatten_lessons` (Slice 1).
- Produces (in `backend/srs.py`):
  - `QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}`.
  - `sm2(reviews) -> {"repetitions", "interval_days", "ease_factor", "last_reviewed", "next_review"}` where `reviews` is a chronological list of `{"quality": str, "date": datetime.date}`; `next_review`/`last_reviewed` are `datetime.date | None`.
  - `due_lesson_ids(conn, content_dir, course_id, today=None) -> [lesson_id]` in manifest order.
  - `reviews_due_count(conn, content_dir, course_id, today=None) -> int`.

- [ ] **Step 1: Write the failing test** `tests/test_srs.py`:

```python
import datetime
import json
from backend import srs, courses, events

D = datetime.date


def _rev(q, d):
    return {"quality": q, "date": d}


def test_sm2_first_good_schedules_one_day():
    s = srs.sm2([_rev("good", D(2026, 1, 1))])
    assert s["interval_days"] == 1
    assert s["repetitions"] == 1
    assert s["next_review"] == D(2026, 1, 2)


def test_sm2_progresses_1_6_then_ef():
    revs = [_rev("good", D(2026, 1, 1)), _rev("good", D(2026, 1, 2)), _rev("good", D(2026, 1, 8))]
    s = srs.sm2(revs)
    # reps: 1 (I=1), 2 (I=6), 3 (I=round(6*2.5)=15)
    assert s["repetitions"] == 3
    assert s["interval_days"] == 15
    assert s["next_review"] == D(2026, 1, 23)


def test_sm2_again_resets_and_due_same_day():
    revs = [_rev("good", D(2026, 1, 1)), _rev("good", D(2026, 1, 2)), _rev("again", D(2026, 1, 8))]
    s = srs.sm2(revs)
    assert s["repetitions"] == 0
    assert s["interval_days"] == 0
    assert s["next_review"] == D(2026, 1, 8)  # due today
    assert s["ease_factor"] < 2.5  # a fail lowers ease


def test_sm2_easy_raises_ease():
    s = srs.sm2([_rev("easy", D(2026, 1, 1))])
    assert s["ease_factor"] > 2.5


def _fixture(tmp_path):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "demo-l1", "title": "L1"}, {"id": "demo-l2", "title": "L2"}]}],
    }))
    return root


def _review_event(cid, lid, quality, when):
    return {
        "client_event_id": f"{lid}-{when}", "session_id": "s1",
        "event_type": "lesson_reviewed", "occurred_at": when,
        "course_id": cid, "topic_id": lid, "payload": {"quality": quality},
    }


def test_due_lesson_ids_reflects_schedule(conn, tmp_path):
    root = _fixture(tmp_path)
    # l1 reviewed 'good' yesterday -> due in 1 day -> due today; l2 never reviewed -> not due
    events.insert_events(conn, [_review_event("demo", "demo-l1", "good", "2026-01-01T09:00:00+00:00")])
    due = srs.due_lesson_ids(conn, root, "demo", today=D(2026, 1, 2))
    assert due == ["demo-l1"]
    assert srs.reviews_due_count(conn, root, "demo", today=D(2026, 1, 2)) == 1
    # before the due date, nothing is due
    assert srs.due_lesson_ids(conn, root, "demo", today=D(2026, 1, 1)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_srs.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.srs`.

- [ ] **Step 3: Write `backend/srs.py`:**

```python
import datetime
import json

from backend import courses

QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}


def sm2(reviews):
    ef = 2.5
    reps = 0
    interval = 0
    last = None
    for r in reviews:
        q = QUALITY.get(r["quality"], 4)
        last = r["date"]
        if q < 3:
            reps = 0
            interval = 0  # due again the same day
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = round(interval * ef)
            reps += 1
        ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        if ef < 1.3:
            ef = 1.3
    next_review = last + datetime.timedelta(days=interval) if last is not None else None
    return {
        "repetitions": reps,
        "interval_days": interval,
        "ease_factor": round(ef, 2),
        "last_reviewed": last,
        "next_review": next_review,
    }


def _reviews_by_lesson(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'lesson_reviewed' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    out = {}
    for row in rows:
        if not row["topic_id"]:
            continue
        payload = json.loads(row["payload"]) if row["payload"] else {}
        quality = payload.get("quality", "good")
        date = datetime.date.fromisoformat(row["occurred_at"][:10])
        out.setdefault(row["topic_id"], []).append({"quality": quality, "date": date})
    return out


def due_lesson_ids(conn, content_dir, course_id, today=None):
    today = today or datetime.date.today()
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return []
    by_lesson = _reviews_by_lesson(conn, course_id)
    due = []
    for lesson in courses.flatten_lessons(manifest):
        revs = by_lesson.get(lesson["id"])
        if not revs:
            continue
        sched = sm2(revs)
        if sched["next_review"] is not None and sched["next_review"] <= today:
            due.append(lesson["id"])
    return due


def reviews_due_count(conn, content_dir, course_id, today=None):
    return len(due_lesson_ids(conn, content_dir, course_id, today))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_srs.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/srs.py tests/test_srs.py
git commit -m "feat(backend): SM-2 spaced-repetition scheduler from review events

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire reviews into progress + a reviews endpoint

**What / Why / Verify:** Make "reviews due" real and expose the due list. *Verify:* a reviewed lesson counts as done; `GET /api/courses/<id>/reviews` returns due ids; `/api/courses` reports a real `reviewsDue`.

**Files:**
- Modify: `backend/courses.py`
- Modify: `backend/app.py`
- Test: `tests/test_courses.py` (extend), `tests/test_courses_api.py` (extend)

**Interfaces:**
- Consumes: `srs.reviews_due_count`, `srs.due_lesson_ids` (Task 1).
- Produces: `completed_lesson_ids` counts `lesson_completed` + `lesson_reviewed`; `list_courses` summaries carry a real `reviewsDue`; `GET /api/courses/<course_id>/reviews` → `{"due": [...]}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_courses.py`:
```python
def test_completed_counts_reviewed_events(conn, tmp_path):
    from backend import courses, events
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(__import__("json").dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    events.insert_events(conn, [{
        "client_event_id": "r1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-01-01T09:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    assert "demo-l1" in courses.completed_lesson_ids(conn, "demo")
```

Append to `tests/test_courses_api.py` (reuses the `_fixture_course` helper added in Slice 3):
```python
def test_reviews_endpoint_lists_due(client, tmp_path, monkeypatch):
    from backend import courses, events
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    # a review far in the past -> due now
    events.insert_events(courses.db.get_connection(client.application.config.get("DB_PATH"))
                         if False else __import__("backend.db", fromlist=["db"]).get_connection(":memory:"), [])  # placeholder, replaced below
```

> NOTE for the implementer: the API test must insert the `lesson_reviewed` event into the **same** database the `client` uses. The `client` fixture builds the app with `db_path=tmp_path/"test_api.db"`. Insert via that path. Use this concrete version instead of the placeholder above:

```python
def test_reviews_endpoint_lists_due(client, tmp_path, monkeypatch):
    from backend import courses, events, db
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)

    # insert a long-past review into the SAME db the client app uses
    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-1", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2020-01-01T09:00:00+00:00", "course_id": manifest["id"],
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()

    due = client.get(f"/api/courses/{manifest['id']}/reviews").get_json()["due"]
    assert due == [lesson_id]
    listed = client.get("/api/courses").get_json()["courses"]
    found = next(c for c in listed if c["id"] == manifest["id"])
    assert found["reviewsDue"] == 1
```

> The `client` fixture must expose the db path as `app.config["DB_PATH"]`. Update `tests/conftest.py`'s `client` fixture to set `app.config["DB_PATH"] = tmp_path / "test_api.db"` right after creating the app (it already passes that path to `create_app`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_courses.py -k reviewed tests/test_courses_api.py -k reviews_endpoint -v`
Expected: FAIL — `completed_lesson_ids` ignores `lesson_reviewed`; `/reviews` route is 404; `reviewsDue` is 0.

- [ ] **Step 3: Update `tests/conftest.py`** — in the `client` fixture, expose the db path:

```python
@pytest.fixture
def client(tmp_path):
    from backend.app import create_app

    db_path = tmp_path / "test_api.db"
    app = create_app(db_path=db_path)
    app.config.update(TESTING=True, DB_PATH=db_path)
    return app.test_client()
```

- [ ] **Step 4: Update `backend/courses.py`** — count both event types, and report real `reviewsDue`:

Change `completed_lesson_ids`'s query:
```python
def completed_lesson_ids(conn, course_id):
    rows = conn.execute(
        "SELECT DISTINCT topic_id FROM events "
        "WHERE event_type IN ('lesson_completed', 'lesson_reviewed') AND course_id = ?",
        (course_id,),
    ).fetchall()
    return {r["topic_id"] for r in rows if r["topic_id"]}
```

In `list_courses`, replace `"reviewsDue": 0` with a real count (lazy import avoids a circular import, since `srs` imports `courses`):
```python
            from backend import srs
            summaries.append({
                "id": manifest["id"],
                "title": manifest["title"],
                "subtitle": manifest.get("subtitle", ""),
                "progress": {k: progress[k] for k in ("done", "total", "pct")},
                "nextLesson": progress["nextLesson"],
                "reviewsDue": srs.reviews_due_count(conn, content_dir, child.name),
            })
```

- [ ] **Step 5: Add the reviews route to `backend/app.py`** — update the import line to include `srs`, and add the route after `get_lesson`:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs
```
```python
    @app.get("/api/courses/<course_id>/reviews")
    def get_reviews(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            due = srs.due_lesson_ids(conn, courses.CONTENT_DIR, course_id)
        finally:
            conn.close()
        return jsonify({"due": due})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_courses.py tests/test_courses_api.py tests/test_srs.py -v` then `.venv/bin/pytest -q`
Expected: PASS (all backend).

- [ ] **Step 7: Commit**

```bash
git add backend/courses.py backend/app.py tests/conftest.py tests/test_courses.py tests/test_courses_api.py
git commit -m "feat(backend): real reviews-due count + reviews endpoint; reviewed counts as done

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Recall rating on lesson finish + review-session flow

**What / Why / Verify:** Replace the lesson's "Continue" with a four-button recall rating that logs `lesson_reviewed`, and make the dashboard Review button run a session over the due lessons. *Verify (unit):* the lesson view renders the four `data-quality` rating buttons once the solution is revealed (and a disabled finish hint before). *Verify (real app):* deferred to Task 4.

**Files:**
- Modify: `frontend/src/views/lesson.js`
- Modify: `frontend/src/courses.js`
- Modify: `frontend/src/app.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/views.test.js` (extend), `frontend/tests/courses.test.js` (extend)

**Interfaces:**
- Consumes: `loadLesson` (Slice 1), `buildEvent` payload support (Slice 1), the existing lesson screen.
- Produces: `lessonHTML` renders a `.rate` block with four `button[data-quality="again|hard|good|easy"]` when `state.solutionRevealed`; `frontend/src/courses.js` gains `loadReviews({fetch, courseId}) -> Promise<string[]>` (GET `/api/courses/<id>/reviews`, returns `body.due || []`).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/views.test.js`:
```javascript
test("lesson shows the recall rating once the solution is revealed", () => {
  const revealed = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.match(revealed, /data-quality="again"/);
  assert.match(revealed, /data-quality="hard"/);
  assert.match(revealed, /data-quality="good"/);
  assert.match(revealed, /data-quality="easy"/);
  assert.match(revealed, /recall/i);

  const notYet = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(notYet, /data-quality=/);
});
```

Append to `frontend/tests/courses.test.js`:
```javascript
import { loadReviews } from "../src/courses.js";

test("loadReviews returns the due array", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ due: ["c-l1", "c-l2"] }) }; };
  const due = await loadReviews({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/reviews");
  assert.deepEqual(due, ["c-l1", "c-l2"]);
});

test("loadReviews returns [] on non-ok", async () => {
  assert.deepEqual(await loadReviews({ fetch: async () => ({ ok: false, status: 500 }), courseId: "c" }), []);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && node --test tests/views.test.js tests/courses.test.js`
Expected: FAIL — `data-quality` not rendered; `loadReviews` not exported.

- [ ] **Step 3: Update `frontend/src/views/lesson.js`** — replace the `.nav` block (lines 44–47) with a Back button plus, when revealed, the rating; otherwise a disabled finish hint:

```javascript
    <div class="nav">
      <button class="btn-back" data-action="back">Back</button>
      ${
        state.solutionRevealed
          ? `<div class="rate" role="group" aria-label="Rate recall">
               <span class="rate-q">How well did you recall this?</span>
               <button class="rate-btn" data-quality="again">Again</button>
               <button class="rate-btn" data-quality="hard">Hard</button>
               <button class="rate-btn" data-quality="good">Good</button>
               <button class="rate-btn" data-quality="easy">Easy</button>
             </div>`
          : `<button class="btn-primary" data-action="continue" disabled>Reveal solution to finish</button>`
      }
    </div>
```

- [ ] **Step 4: Add `loadReviews` to `frontend/src/courses.js`:**

```javascript
export async function loadReviews({ fetch, courseId }) {
  const resp = await fetch(`/api/courses/${courseId}/reviews`);
  if (!resp.ok) return [];
  const body = await resp.json();
  return body.due || [];
}
```

- [ ] **Step 5: Wire the rating + review session into `frontend/src/app.js`.**

Update the courses import:
```javascript
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews } from "./courses.js";
```

Add `reviewQueue: []` to the `ui` object initializer.

In `paintLesson`, replace the `data-action="continue"` handler block with rating handlers (the continue button only exists, disabled, before reveal — so guard for null):
```javascript
    view.querySelectorAll('[data-quality]').forEach((btn) => {
      btn.addEventListener("click", async () => {
        const quality = btn.getAttribute("data-quality");
        log("lesson_reviewed", { courseId: ui.courseId, topicId: ui.lesson.id, payload: { quality } });
        await doFlush();
        await advanceAfterLesson();
      });
    });
```

Add the advance + review-session functions (near `startLesson`):
```javascript
  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (!ui.lesson) { await refreshSummary(); showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    showCourse();
  }

  async function startReviewSession() {
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (!ui.lesson) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

In `startLesson`, set `ui.reviewQueue = []` (a normal study session is not a review) — add the line right after `if (!next) return;`:
```javascript
    ui.reviewQueue = [];
```

In `paintCourse`, change the review button handler from logging to starting the session:
```javascript
    view.querySelector('[data-action="review"]').addEventListener("click", startReviewSession);
```

- [ ] **Step 6: Add rating styles** — append to `frontend/styles.css`:

```css
/* =================  RECALL RATING  ================= */
.rate{display:flex; flex-wrap:wrap; align-items:center; gap:8px}
.rate-q{flex:1 1 100%; font-size:13px; color:var(--text-mut); margin-bottom:2px}
.rate-btn{flex:1; min-width:64px; padding:11px 8px; border:1px solid var(--border-field); border-radius:var(--r-sm);
  background:var(--glass-field); color:var(--text); font:600 14px/1 inherit; cursor:pointer; transition:all .15s}
.rate-btn:hover{background:rgba(255,255,255,.7)}
.rate-btn:active{transform:translateY(1px)}
```

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && node --test`
Expected: PASS (all suites incl. the new view + courses tests).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/lesson.js frontend/src/courses.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js frontend/tests/courses.test.js
git commit -m "feat(frontend): recall rating on lesson finish + review session flow

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: End-to-end verification + deploy

**What / Why / Verify:** Prove the loop in a real browser, then ship to the Pi. *Verify:* finishing a lesson with a rating schedules it; an `again` (or past-due) makes it appear in "reviews due"; the Review flow re-presents it.

**Files:** none changed (verification + deploy).

- [ ] **Step 1: Full local test sweep**

Run: `.venv/bin/pytest -q` → PASS. `cd frontend && node --test` → PASS.

- [ ] **Step 2: Run locally** — `.venv/bin/waitress-serve --port=8222 --call backend.app:create_app` (background).

- [ ] **Step 3: Real-browser check (Playwright, against `http://localhost:8222/`)**

1. Create a tiny course via the chat (or reuse one), open it, Start session → reach a lesson.
2. Type an answer → Reveal solution → the **four recall buttons** appear. Click **Again**.
3. Back on the course screen, **Reviews due** shows ≥ 1 (an `again` is due same-day).
4. Click **Review** → the due lesson is re-presented through the lesson screen. Reveal → rate **Good** → returns to the course; Reviews due decremented.
5. Snapshot the lesson screen showing the rating row and the dashboard showing a non-zero Reviews due.

- [ ] **Step 4: Stop the local server.**

- [ ] **Step 5: Deploy to the Pi**

```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then `mcp__pi-ssh__sudo-exec: systemctl restart claude-university` and confirm `systemctl is-active`.

- [ ] **Step 6: Verify on the Pi** — `curl -s http://localhost:8200/api/health` → ok; open `http://100.99.33.106:8200/`, and (with a course that has a reviewed lesson) confirm `GET /api/courses/<id>/reviews` returns due ids and the dashboard shows a real Reviews-due count.

---

## Self-Review

**1. Spec coverage:**
- SM-2 scheduler from `lesson_reviewed` events → Task 1. ✓
- Real per-course `reviewsDue` + reviews endpoint → Task 2. ✓
- `completed` counts both event types (back-compat) → Task 2. ✓
- Recall rating on lesson finish (4 buttons → `lesson_reviewed{quality}`) → Task 3. ✓
- Review session re-presenting due lessons through the existing screen; study & review unified → Task 3 (`startReviewSession`/`advanceAfterLesson`). ✓
- Derived-from-events, no schema change, SM-2 mapping, `again` due-same-day → Tasks 1–2 + Global Constraints. ✓
- *Correctly deferred:* auto-grading (Slice 5), mastery/adaptivity (Slice 6), global review queue + player UX (Slice 7), FSRS/suspend/options.

**2. Placeholder scan:** No "TBD/TODO". The API-test step shows a placeholder snippet then immediately replaces it with the concrete version and a NOTE — the concrete `test_reviews_endpoint_lists_due` is the one to implement; the placeholder line is explicitly discarded.

**3. Type consistency:** `srs.sm2(reviews)` consumes `{"quality","date"}` dicts and returns the documented keys; `due_lesson_ids`/`reviews_due_count(conn, content_dir, course_id, today=None)` match their call sites in `courses.list_courses` (lazy import) and `app.get_reviews`. `lesson_reviewed` event shape (`course_id`, `topic_id`, `payload.quality`) is produced by `app.js` (`log("lesson_reviewed", {courseId, topicId, payload:{quality}})`), persisted by the existing `insert_events`, and read by `srs._reviews_by_lesson`. `loadReviews` returns `body.due` which `get_reviews` produces. `QUALITY` keys match the four `data-quality` button values. The lazy `from backend import srs` inside `list_courses` avoids the `srs ↔ courses` import cycle.
