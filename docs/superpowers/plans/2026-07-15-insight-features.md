# Insight Features Implementation Plan (streak, reviews banner, activity log)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the learner honest, motivating feedback about their own study behaviour: a real study-streak stat on the course dashboard, a "reviews due" banner on Home, and a recent-activity study log — all derived from the events table that already records everything.

**Architecture:** One new backend module `backend/stats.py` (derived learner stats read from `events`), two new JSON routes in `app.py` (`GET /api/stats`, `GET /api/activity`), one new frontend API helper module (`frontend/src/stats.js`), one new view (`frontend/src/views/activity.js`), and small additions to `dashboard.js`, `home.js`, `app.js`, and `styles.css`. No Claude generation is involved anywhere in this plan — every feature is a cheap DB read.

**Tech Stack:** Flask + SQLite backend (pytest), plain ES-module frontend (node:test). No new dependencies.

## Global Constraints

- **Never merge to main or push without Werner's explicit approval.** Work on branch `feat/insight-features` (already created off main). Committing per task on this branch is expected.
- **No emojis anywhere** — code, UI copy, commit messages.
- **All learner/model-derived text rendered into HTML client-side must go through `esc()`** from `frontend/src/escape.js`. Course titles and lesson titles from manifests are NOT server-sanitized — always `esc()` them in views.
- Backend tests: `.venv/bin/pytest` from the repo root (currently 235 passing — must stay green).
- Frontend tests: `node --test frontend/tests/*.test.js` (currently 123 passing — must stay green). NEVER run `node --test frontend/tests/` (bare directory) — it silently runs nothing.
- Date convention: events store `occurred_at` as ISO-8601 UTC (`new Date().toISOString()`). Backend date bucketing uses `occurred_at[:10]` (the UTC day) — the same convention `backend/srs.py` already uses. Do not introduce timezone conversion in the backend.
- Follow existing patterns: routes open a connection with `db.get_connection(path)` and close it in `finally`; frontend fetch helpers return safe fallbacks on `!resp.ok` (see `frontend/src/courses.js`); views are pure functions returning HTML strings.
- Keep functions under ~30 lines; no magic numbers without a named constant.

## Design decisions (already made — implement as stated)

- **A streak day = a day the learner actually studied**, defined as at least one event of type `lesson_view` or `lesson_reviewed` on that UTC day. `session_start` does NOT count (opening the app is not studying).
- **A streak survives until a full day is missed**: if the last study day is today or yesterday, the streak is alive and counts consecutive days back from that day. If the last study day is 2+ days ago, the streak is 0.
- **The activity log shows four event types**: `lesson_view` ("Studied"), `lesson_reviewed` ("Completed"), `course_created` ("Created course"), `course_revised` ("Revised course"). Other event types (checks, hints, timers) are noise and are excluded server-side.
- Activity entries are resolved to display strings **server-side** (course title + lesson title from manifests) so the client makes exactly one fetch and does no joins.
- The activity view groups entries by the browser's **local** day ("Today" / "Yesterday" / weekday label) since that is what reads naturally to the learner; the backend stays UTC.

---

### Task 1: `backend/stats.py` — `streak_days`

**Files:**
- Create: `backend/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Produces: `stats.streak_days(conn, today=None) -> int` — `conn` is a sqlite3 connection with the standard schema; `today` is an optional `datetime.date` for tests (defaults to the current UTC date). Task 3 calls this from a route.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stats.py`:

```python
import datetime

from backend import events, stats


def _ev(i, event_type, occurred_at, course_id="c1", topic_id="c1-l1"):
    return {
        "client_event_id": f"e{i}",
        "session_id": "s1",
        "event_type": event_type,
        "occurred_at": occurred_at,
        "course_id": course_id,
        "topic_id": topic_id,
    }


TODAY = datetime.date(2026, 7, 15)


def test_streak_zero_with_no_events(conn):
    assert stats.streak_days(conn, today=TODAY) == 0


def test_streak_one_for_study_today(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-15T09:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_streak_alive_if_last_study_was_yesterday(conn):
    events.insert_events(conn, [_ev(1, "lesson_reviewed", "2026-07-14T21:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_streak_dead_if_last_study_two_days_ago(conn):
    events.insert_events(conn, [_ev(1, "lesson_view", "2026-07-13T21:00:00+00:00")])
    assert stats.streak_days(conn, today=TODAY) == 0


def test_streak_counts_consecutive_days(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-13T10:00:00+00:00"),
        _ev(2, "lesson_reviewed", "2026-07-14T10:00:00+00:00"),
        _ev(3, "lesson_view", "2026-07-15T10:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 3


def test_streak_stops_at_gap(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-11T10:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-12T10:00:00+00:00"),
        # 2026-07-13 missed
        _ev(3, "lesson_view", "2026-07-14T10:00:00+00:00"),
        _ev(4, "lesson_view", "2026-07-15T10:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 2


def test_multiple_events_same_day_count_once(conn):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_view", "2026-07-15T11:00:00+00:00"),
        _ev(3, "lesson_reviewed", "2026-07-15T12:00:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_non_study_events_do_not_count(conn):
    events.insert_events(conn, [
        _ev(1, "session_start", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_check", "2026-07-15T09:05:00+00:00"),
        _ev(3, "hint_revealed", "2026-07-15T09:06:00+00:00"),
    ])
    assert stats.streak_days(conn, today=TODAY) == 0
```

The `conn` fixture already exists in `tests/conftest.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.stats'` (or `AttributeError`).

- [ ] **Step 3: Write the implementation**

Create `backend/stats.py`:

```python
import datetime

# A streak day is a day the learner actually studied — opened a lesson or
# completed a review. session_start (just opening the app) does not count.
STUDY_EVENTS = ("lesson_view", "lesson_reviewed")


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def streak_days(conn, today=None):
    """Consecutive UTC days with study activity, anchored at today or yesterday.

    The streak survives until a full day is missed: studying yesterday but not
    yet today keeps it alive. Returns 0 when the last study day is 2+ days ago.
    """
    today = today or _utc_today()
    placeholders = ",".join("?" * len(STUDY_EVENTS))
    rows = conn.execute(
        f"SELECT DISTINCT substr(occurred_at, 1, 10) AS day FROM events "
        f"WHERE event_type IN ({placeholders}) ORDER BY day DESC",
        STUDY_EVENTS,
    ).fetchall()
    days = []
    for r in rows:
        try:
            days.append(datetime.date.fromisoformat(r["day"]))
        except ValueError:
            continue  # malformed timestamp — skip rather than crash the dashboard
    if not days or days[0] < today - datetime.timedelta(days=1):
        return 0
    streak = 1
    for prev, cur in zip(days, days[1:]):
        if prev - cur != datetime.timedelta(days=1):
            break
        streak += 1
    return streak
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest`
Expected: all green (235 existing + 8 new).

- [ ] **Step 6: Commit**

```bash
git add backend/stats.py tests/test_stats.py
git commit -m "feat(stats): streak_days — consecutive UTC study days from events"
```

---

### Task 2: `backend/stats.py` — `recent_activity`

**Files:**
- Modify: `backend/stats.py`
- Test: `tests/test_stats.py` (append)

**Interfaces:**
- Consumes: `courses.load_manifest(content_dir, course_id)`, `courses.flatten_lessons(manifest)` (both exist in `backend/courses.py`).
- Produces: `stats.recent_activity(conn, content_dir, limit=50) -> list[dict]`, newest first, each dict: `{"occurredAt": str, "type": str, "courseTitle": str|None, "lessonTitle": str|None, "quality": str|None}`. Task 3 calls this from a route.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stats.py`:

```python
import json


def _write_course(tmp_path):
    course = {
        "id": "c1",
        "title": "Machine Learning",
        "modules": [
            {"id": "m1", "title": "Foundations", "lessons": [
                {"id": "c1-l1", "title": "What is learning?"},
            ]},
        ],
    }
    d = tmp_path / "c1"
    d.mkdir(parents=True)
    (d / "course.json").write_text(json.dumps(course))
    return tmp_path


def test_activity_newest_first_with_resolved_titles(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-14T10:00:00+00:00"),
        _ev(2, "lesson_reviewed", "2026-07-15T10:00:00+00:00"),
    ])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e2'",
        (json.dumps({"quality": "good"}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert [e["type"] for e in out] == ["lesson_reviewed", "lesson_view"]
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] == "What is learning?"
    assert out[0]["quality"] == "good"
    assert out[1]["quality"] is None


def test_activity_excludes_noise_event_types(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "session_start", "2026-07-15T09:00:00+00:00"),
        _ev(2, "lesson_check", "2026-07-15T09:05:00+00:00"),
        _ev(3, "lesson_view", "2026-07-15T09:10:00+00:00"),
    ])
    out = stats.recent_activity(conn, content, limit=10)
    assert [e["type"] for e in out] == ["lesson_view"]


def test_activity_respects_limit(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(i, "lesson_view", f"2026-07-15T0{i}:00:00+00:00") for i in range(1, 6)
    ])
    out = stats.recent_activity(conn, content, limit=3)
    assert len(out) == 3
    assert out[0]["occurredAt"].startswith("2026-07-15T05")


def test_activity_falls_back_to_ids_for_missing_course(conn, tmp_path):
    events.insert_events(conn, [
        _ev(1, "lesson_view", "2026-07-15T10:00:00+00:00",
            course_id="deleted-course", topic_id="deleted-course-l9"),
    ])
    out = stats.recent_activity(conn, tmp_path, limit=10)
    assert out[0]["courseTitle"] == "deleted-course"
    assert out[0]["lessonTitle"] is None


def test_activity_course_created_has_no_lesson(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "course_created", "2026-07-15T10:00:00+00:00", topic_id=None),
    ])
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "course_created"
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: the 5 new tests FAIL with `AttributeError: module 'backend.stats' has no attribute 'recent_activity'`; the 8 Task-1 tests still pass.

- [ ] **Step 3: Write the implementation**

Add to `backend/stats.py` (new imports at top: `import json` and `from backend import courses`):

```python
# Event types worth showing in the study log. Checks, hints, and timer ticks
# are noise at log granularity and are filtered out here, server-side.
ACTIVITY_EVENTS = ("lesson_view", "lesson_reviewed", "course_created", "course_revised")


def _course_titles(content_dir, course_id, cache):
    if course_id not in cache:
        manifest = courses.load_manifest(content_dir, course_id)
        if manifest is None:
            cache[course_id] = (course_id, {})  # deleted/renamed course — show raw id
        else:
            cache[course_id] = (
                manifest.get("title") or course_id,
                {l["id"]: l["title"] for l in courses.flatten_lessons(manifest)},
            )
    return cache[course_id]


def recent_activity(conn, content_dir, limit=50):
    """Newest-first study log entries with titles resolved from course manifests."""
    placeholders = ",".join("?" * len(ACTIVITY_EVENTS))
    rows = conn.execute(
        f"SELECT course_id, topic_id, event_type, occurred_at, payload FROM events "
        f"WHERE event_type IN ({placeholders}) ORDER BY occurred_at DESC, id DESC LIMIT ?",
        (*ACTIVITY_EVENTS, limit),
    ).fetchall()
    cache = {}
    out = []
    for r in rows:
        course_title, lesson_titles = (None, {})
        if r["course_id"]:
            course_title, lesson_titles = _course_titles(content_dir, r["course_id"], cache)
        payload = json.loads(r["payload"]) if r["payload"] else {}
        out.append({
            "occurredAt": r["occurred_at"],
            "type": r["event_type"],
            "courseTitle": course_title,
            "lessonTitle": lesson_titles.get(r["topic_id"]) if r["topic_id"] else None,
            "quality": payload.get("quality"),
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/stats.py tests/test_stats.py
git commit -m "feat(stats): recent_activity — newest-first study log with resolved titles"
```

---

### Task 3: Routes `GET /api/stats` and `GET /api/activity`

**Files:**
- Modify: `backend/app.py` (add two routes after the `get_events` route; add `stats` to the existing `from backend import ...` line)
- Test: `tests/test_api.py` (append)

**Interfaces:**
- Consumes: `stats.streak_days(conn)`, `stats.recent_activity(conn, courses.CONTENT_DIR, limit=...)` from Tasks 1–2.
- Produces: `GET /api/stats` → `{"streakDays": int}`; `GET /api/activity?limit=N` → `{"activity": [entry, ...]}`. The frontend (Tasks 4 and 6) consumes exactly these shapes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py` (the `client` fixture comes from conftest; the new tests import what they need locally, so no top-of-file changes are required):

```python
def test_stats_streak_from_study_events(client):
    client.post("/api/events", json={"events": [{
        "client_event_id": "st1", "session_id": "s1",
        "event_type": "lesson_view", "occurred_at": "2026-06-21T10:00:00+00:00",
    }]})
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["streakDays"], int)


def test_activity_returns_resolved_entries(client, tmp_path, monkeypatch):
    import json as _json
    from backend import courses
    root = tmp_path / "content"
    d = root / "c1"
    d.mkdir(parents=True)
    (d / "course.json").write_text(_json.dumps({
        "id": "c1", "title": "Machine Learning",
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "c1-l1", "title": "Intro"}]}],
    }))
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    client.post("/api/events", json={"events": [{
        "client_event_id": "ac1", "session_id": "s1", "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00", "course_id": "c1", "topic_id": "c1-l1",
    }]})
    resp = client.get("/api/activity?limit=10")
    assert resp.status_code == 200
    entries = resp.get_json()["activity"]
    assert entries[0]["courseTitle"] == "Machine Learning"
    assert entries[0]["lessonTitle"] == "Intro"


def test_activity_limit_is_bounded_and_tolerant(client):
    assert client.get("/api/activity?limit=99999").status_code == 200
    assert client.get("/api/activity?limit=banana").status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: new tests FAIL with 404 on `/api/stats` and `/api/activity`.

- [ ] **Step 3: Write the routes**

In `backend/app.py`, add `stats` to the import line:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats
```

Add after the `get_events` route:

```python
    @app.get("/api/stats")
    def get_stats():
        conn = db.get_connection(path)
        try:
            streak = stats.streak_days(conn)
        finally:
            conn.close()
        return jsonify({"streakDays": streak})

    @app.get("/api/activity")
    def get_activity():
        try:
            limit = min(int(request.args.get("limit", 50)), 200)
        except ValueError:
            limit = 50
        conn = db.get_connection(path)
        try:
            activity = stats.recent_activity(conn, courses.CONTENT_DIR, limit=limit)
        finally:
            conn.close()
        return jsonify({"activity": activity})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py tests/test_stats.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_api.py
git commit -m "feat(api): GET /api/stats (streak) and GET /api/activity (study log)"
```

---

### Task 4: Frontend — streak tile on the course dashboard

**Files:**
- Create: `frontend/src/stats.js`
- Modify: `frontend/src/views/dashboard.js` (third stat tile), `frontend/src/app.js` (fetch stats in `refreshSummary`, expose `streakDays` in `sessionData`)
- Test: create `frontend/tests/stats.test.js`; append to `frontend/tests/views.test.js`

**Interfaces:**
- Consumes: `GET /api/stats` → `{"streakDays": int}` (Task 3).
- Produces: `loadStats({ fetch }) -> Promise<{streakDays: number}>` and `loadActivity({ fetch, limit }) -> Promise<entry[]>` (the latter is consumed by Task 6); `dashboardHTML` now reads `data.streakDays`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/stats.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadStats, loadActivity } from "../src/stats.js";

const okFetch = (body) => async () => ({ ok: true, json: async () => body });
const badFetch = async () => ({ ok: false, json: async () => ({}) });

test("loadStats returns the body on success", async () => {
  const stats = await loadStats({ fetch: okFetch({ streakDays: 4 }) });
  assert.equal(stats.streakDays, 4);
});

test("loadStats falls back to zero streak on failure", async () => {
  const stats = await loadStats({ fetch: badFetch });
  assert.equal(stats.streakDays, 0);
});

test("loadActivity returns entries and passes limit", async () => {
  let url = null;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ activity: [{ type: "lesson_view" }] }) }; };
  const entries = await loadActivity({ fetch, limit: 25 });
  assert.equal(entries.length, 1);
  assert.equal(url, "/api/activity?limit=25");
});

test("loadActivity returns empty list on failure", async () => {
  assert.deepEqual(await loadActivity({ fetch: badFetch }), []);
});
```

Append to `frontend/tests/views.test.js` — it already imports `dashboardHTML` and defines the fixtures `DASHBOARD_SEED` (dashboard data) and `idleTimer` (timer view); use them verbatim:

```js
test("dashboard shows the streak tile with day count", () => {
  const html = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 4 }, idleTimer);
  assert.match(html, /STREAK/);
  assert.match(html, />4</);
  assert.match(html, /days/);
});

test("dashboard streak uses singular day and a nudge at zero", () => {
  const one = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 1 }, idleTimer);
  assert.match(one, /day</);
  assert.doesNotMatch(one, /days</);
  const zero = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 0 }, idleTimer);
  assert.match(zero, /Study today to start one/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: new tests FAIL (`stats.js` missing; STREAK not in dashboard HTML). All existing tests still pass.

- [ ] **Step 3: Implement**

Create `frontend/src/stats.js`:

```js
export async function loadStats({ fetch }) {
  const resp = await fetch("/api/stats");
  if (!resp.ok) return { streakDays: 0 };
  return resp.json();
}

export async function loadActivity({ fetch, limit = 50 }) {
  const resp = await fetch(`/api/activity?limit=${limit}`);
  if (!resp.ok) return [];
  const body = await resp.json();
  return body.activity || [];
}
```

In `frontend/src/views/dashboard.js`, add a third `<section class="stat">` inside `.stat-row`, after the REVIEWS DUE tile:

```js
      <section class="stat">
        <span class="eyebrow mut">STREAK</span>
        <div style="display:flex; align-items:baseline; gap:6px; margin-top:12px"><span class="big" style="color:var(--purple)">${data.streakDays}</span><span class="unit">day${data.streakDays === 1 ? "" : "s"}</span></div>
        <div class="stat-note">${data.streakDays ? "Consecutive study days" : "Study today to start one"}</div>
      </section>
```

In `frontend/src/app.js`:
1. Add to the imports: `import { loadStats } from "./stats.js";`
2. In `refreshSummary()`, after the manifest reload line, add:

```js
    ui.stats = (await loadStats({ fetch })) || ui.stats;
```

3. In `sessionData()`, add to the returned object:

```js
      streakDays: (ui.stats && ui.stats.streakDays) || 0,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test frontend/tests/*.test.js`
Expected: all green (123 existing + 6 new).

- [ ] **Step 5: Import-resolution check** (app.js has no unit tests — this catches broken imports)

Run from repo root:

```bash
node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"
```

Expected: `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stats.js frontend/src/views/dashboard.js frontend/src/app.js frontend/tests/stats.test.js frontend/tests/views.test.js
git commit -m "feat(dashboard): real study-streak stat tile fed by /api/stats"
```

---

### Task 5: Frontend — reviews-due banner on Home

**Files:**
- Modify: `frontend/src/views/home.js`, `frontend/styles.css`
- Test: `frontend/tests/home.test.js` (append)

**Interfaces:**
- Consumes: the `courses` array `homeHTML` already receives (each course has `reviewsDue` and `title`). No new fetches.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/home.test.js`:

```js
test("home shows a banner summing reviews due across courses", () => {
  const html = homeHTML([
    { ...ML, reviewsDue: 3 },
    { ...ML, id: "x2", title: "Statistics", reviewsDue: 2 },
  ]);
  assert.match(html, /review-banner/);
  assert.match(html, /5 reviews due/);
  assert.match(html, /2 courses/);
});

test("home banner names the course when only one has reviews due", () => {
  const html = homeHTML([{ ...ML, reviewsDue: 1 }]);
  assert.match(html, /1 review due/);
  assert.match(html, /Machine Learning/);
});

test("home banner absent when nothing is due", () => {
  assert.doesNotMatch(homeHTML([ML]), /review-banner/);
});

test("home banner escapes course titles", () => {
  const html = homeHTML([{ ...ML, title: "<b>Evil</b>", reviewsDue: 1 }]);
  assert.doesNotMatch(html, /<b>Evil<\/b>/);
});
```

(`ML` has `reviewsDue: 0` in the existing fixture, so existing tests are unaffected.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the 4 new tests FAIL; everything else passes.

- [ ] **Step 3: Implement**

In `frontend/src/views/home.js`, add above `homeHTML`:

```js
function bannerHTML(courses) {
  const withDue = courses.filter((c) => c.reviewsDue > 0);
  const total = withDue.reduce((n, c) => n + c.reviewsDue, 0);
  if (!total) return "";
  const where = withDue.length === 1 ? esc(withDue[0].title) : `${withDue.length} courses`;
  return `<div class="review-banner"><b>${total} review${total === 1 ? "" : "s"} due</b> in ${where} — a quick review now keeps it stuck.</div>`;
}
```

In `homeHTML`, insert `${bannerHTML(courses)}` between the greeting div and the course grid.

In `frontend/styles.css`, add near the other `.home` / card rules:

```css
.review-banner{background:rgba(47,143,208,.10); border:1px solid rgba(47,143,208,.25); color:var(--blue-text);
  border-radius:var(--r-md); padding:12px 16px; margin-bottom:16px; font-size:14px}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test frontend/tests/*.test.js`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/home.js frontend/styles.css frontend/tests/home.test.js
git commit -m "feat(home): reviews-due banner summing SRS cards across courses"
```

---

### Task 6: Frontend — recent-activity study log view

**Files:**
- Create: `frontend/src/views/activity.js`
- Modify: `frontend/src/views/home.js` (activity link), `frontend/src/app.js` (`showActivity` + binding), `frontend/styles.css`
- Test: create `frontend/tests/activity.test.js`; append one test to `frontend/tests/home.test.js`

**Interfaces:**
- Consumes: `loadActivity({ fetch, limit })` from Task 4; entry shape `{occurredAt, type, courseTitle, lessonTitle, quality}` from Task 2.
- Produces: `activityHTML(entries, { now }) -> string` — `now` is an injected `Date` for testability.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/activity.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { activityHTML } from "../src/views/activity.js";

// Build ISO strings on LOCAL days relative to `now`, so grouping labels are
// deterministic regardless of the machine's timezone.
const NOW = new Date(2026, 6, 15, 14, 0, 0); // local 2026-07-15 14:00
const at = (daysAgo, hour = 10) =>
  new Date(2026, 6, 15 - daysAgo, hour, 0, 0).toISOString();

const STUDY = { occurredAt: at(0), type: "lesson_view", courseTitle: "ML", lessonTitle: "Intro", quality: null };

test("activity groups entries under Today and Yesterday", () => {
  const html = activityHTML([
    STUDY,
    { ...STUDY, occurredAt: at(1), type: "lesson_reviewed", quality: "good" },
  ], { now: NOW });
  assert.match(html, /Today/);
  assert.match(html, /Yesterday/);
});

test("activity renders verbs, titles, and review quality", () => {
  const html = activityHTML([
    STUDY,
    { ...STUDY, type: "lesson_reviewed", quality: "easy" },
    { occurredAt: at(0), type: "course_created", courseTitle: "Stats", lessonTitle: null, quality: null },
    { occurredAt: at(0), type: "course_revised", courseTitle: "Stats", lessonTitle: null, quality: null },
  ], { now: NOW });
  assert.match(html, /Studied/);
  assert.match(html, /Completed/);
  assert.match(html, /rated easy/);
  assert.match(html, /Created course/);
  assert.match(html, /Revised course/);
  assert.match(html, /Intro/);
  assert.match(html, /Stats/);
});

test("activity escapes titles", () => {
  const html = activityHTML([{ ...STUDY, lessonTitle: "<img src=x>", courseTitle: "<b>x</b>" }], { now: NOW });
  assert.doesNotMatch(html, /<img src=x>/);
  assert.doesNotMatch(html, /<b>x<\/b>/);
});

test("activity shows an empty state", () => {
  assert.match(activityHTML([], { now: NOW }), /Nothing here yet/);
});
```

Append to `frontend/tests/home.test.js`:

```js
test("home shows the recent-activity link", () => {
  assert.match(homeHTML([ML]), /data-action="activity"/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: new tests FAIL (`activity.js` missing; no activity link on home).

- [ ] **Step 3: Implement the view**

Create `frontend/src/views/activity.js`:

```js
import { esc } from "../escape.js";

const VERBS = {
  lesson_view: "Studied",
  lesson_reviewed: "Completed",
  course_created: "Created course",
  course_revised: "Revised course",
};

function dayKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayLabel(d, now) {
  const key = dayKey(d);
  if (key === dayKey(now)) return "Today";
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (key === dayKey(yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function entryHTML(e) {
  const when = new Date(e.occurredAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const verb = VERBS[e.type] || e.type;
  const what = e.lessonTitle ? esc(e.lessonTitle) : (e.courseTitle ? esc(e.courseTitle) : "");
  const context = e.lessonTitle && e.courseTitle ? `<span class="act-course">${esc(e.courseTitle)}</span>` : "";
  const quality = e.quality ? `<span class="act-quality">rated ${esc(e.quality)}</span>` : "";
  return `<div class="act-entry"><span class="act-time">${when}</span>` +
    `<span class="act-text"><b>${verb}</b> ${what} ${context}${quality}</span></div>`;
}

export function activityHTML(entries, { now = new Date() } = {}) {
  const head = `<div class="greeting"><h1>Recent activity</h1><span>Your study log</span></div>`;
  if (!entries.length) {
    return `<div class="activity">${head}` +
      `<div class="card"><div class="prompt">Nothing here yet — study a lesson and it will show up.</div></div></div>`;
  }
  const groups = [];
  for (const e of entries) {
    const d = new Date(e.occurredAt);
    const label = dayLabel(d, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(e);
    else groups.push({ label, items: [e] });
  }
  const body = groups.map((g) =>
    `<section class="card act-day"><span class="eyebrow mut">${esc(g.label).toUpperCase()}</span>` +
    `${g.items.map(entryHTML).join("")}</section>`,
  ).join("");
  return `<div class="activity">${head}${body}</div>`;
}
```

- [ ] **Step 4: Wire it up**

In `frontend/src/views/home.js`, add below the course grid (inside `.home`):

```js
    <button class="btn-secondary activity-link" data-action="activity">Recent activity</button>
```

In `frontend/src/app.js`:
1. Imports: `import { activityHTML } from "./views/activity.js";` and extend the Task-4 import to `import { loadStats, loadActivity } from "./stats.js";`
2. In `showHome()`, after the add-course binding, add:

```js
    const act = view.querySelector('[data-action="activity"]');
    if (act) act.addEventListener("click", showActivity);
```

3. Add the screen function (near `showHome`), following the app's guard pattern:

```js
  async function showActivity() {
    pauseTimer();
    ui.screen = "activity";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Loading your activity…</div></div>`;
    const entries = await loadActivity({ fetch });
    if (ui.screen !== "activity") return; // navigated away mid-load
    view.innerHTML = activityHTML(entries, { now: new Date() });
  }
```

In `frontend/styles.css`, add:

```css
.activity-link{max-width:240px; margin:18px auto 0; display:block}
.act-day{padding:16px 20px; margin-bottom:14px}
.act-entry{display:flex; gap:12px; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.05); font-size:14px}
.act-entry:last-child{border-bottom:none}
.act-time{color:var(--text-mut); font-variant-numeric:tabular-nums; flex:0 0 52px}
.act-course{color:var(--text-dim); margin-left:6px}
.act-quality{color:var(--blue-text); margin-left:6px}
```

- [ ] **Step 5: Run tests + import check**

Run: `node --test frontend/tests/*.test.js`
Expected: all green.

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/activity.js frontend/src/views/home.js frontend/src/app.js frontend/styles.css frontend/tests/activity.test.js frontend/tests/home.test.js
git commit -m "feat(activity): recent-activity study log view from /api/activity"
```
